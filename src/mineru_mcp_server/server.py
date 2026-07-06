"""MinerU MCP Server — 5 个工具覆盖 DocParse API 全部端点。"""

import os
import shutil
import zipfile
from typing import Any

import requests
from fastmcp import FastMCP

from .client import get_client
from .models import (
    AsyncSubmitInput,
    SyncParseInput,
    TaskQueryInput,
    TaskResultInput,
)

# ── 服务 ───────────────────────────────────────────────
mcp = FastMCP("mineru_mcp")


# ── 工具函数 ───────────────────────────────────────────
def _resolve_output_dir(output_dir: str | None) -> tuple[str | None, dict | None]:
    """解析实际使用的输出目录：优先用户传入值，否则回退 MINERU_OUTPUT_DIR 环境变量。

    Returns:
        (output_dir, error) — 成功时 error 为 None；都未提供时 output_dir 为 None 且 error 是错误 dict。
    """
    resolved = output_dir or os.getenv("MINERU_OUTPUT_DIR")
    if not resolved:
        return None, {
            "success": False,
            "error": "未指定 output_dir，且未设置 MINERU_OUTPUT_DIR 环境变量，无法确定文件保存位置",
        }
    if not os.path.isabs(resolved):
        return None, {
            "success": False,
            "error": f"MINERU_OUTPUT_DIR 必须是绝对路径: {resolved}",
        }
    return resolved, None


def _safe_extract(zf: zipfile.ZipFile, extract_dir: str) -> None:
    """校验 ZIP 内条目不会借由 `../` 等路径穿越写出到 extract_dir 之外，再解压。"""
    extract_dir_abs = os.path.abspath(extract_dir)
    for name in zf.namelist():
        dest = os.path.abspath(os.path.join(extract_dir_abs, name))
        if dest != extract_dir_abs and not dest.startswith(extract_dir_abs + os.sep):
            raise ValueError(f"检测到不安全的 ZIP 路径，已阻止解压: {name}")
    zf.extractall(extract_dir_abs)


def _save_and_extract(
    content: bytes,
    file_name: str,
    output_dir: str,
    extract: bool = True,
) -> dict:
    """将 ZIP 字节写入磁盘并解压。

    Returns:
        {"zip_path": str, "zip_size": int, "extract_dir": str|None, "md_files": [str], "md_count": int}
    """
    os.makedirs(output_dir, exist_ok=True)
    base_name = os.path.splitext(file_name)[0]

    zip_path = os.path.join(output_dir, f"{base_name}.zip")
    with open(zip_path, "wb") as f:
        f.write(content)

    result: dict[str, Any] = {
        "zip_path": zip_path,
        "zip_size": len(content),
        "extract_dir": None,
        "md_files": [],
        "md_count": 0,
    }

    if extract:
        extract_dir = os.path.join(output_dir, base_name)
        if os.path.isdir(extract_dir):
            shutil.rmtree(extract_dir)
        os.makedirs(extract_dir, exist_ok=True)

        with zipfile.ZipFile(zip_path) as z:
            _safe_extract(z, extract_dir)
            for name in z.namelist():
                if name.endswith(".md"):
                    result["md_files"].append(os.path.join(extract_dir, name))

        result["extract_dir"] = extract_dir
        result["md_count"] = len(result["md_files"])

    return result


def _handle_client_error(e: Exception) -> dict:
    """统一错误格式。"""
    if isinstance(e, requests.ConnectionError):
        return {"success": False, "error": "无法连接 MinerU 服务，请确认服务已启动"}
    if isinstance(e, requests.Timeout):
        return {"success": False, "error": "请求超时，文件可能过大，请使用异步接口"}
    if isinstance(e, requests.HTTPError):
        return {
            "success": False,
            "error": f"API 返回 HTTP {e.response.status_code}",
            "detail": e.response.text[:500],
        }
    if isinstance(e, requests.RequestException):
        return {"success": False, "error": f"网络请求失败: {e}"}
    return {"success": False, "error": f"未知错误: {e}"}


# ═══════════════════════════════════════════════════════
# 工具 1: 同步解析
# ═══════════════════════════════════════════════════════
@mcp.tool(
    name="mineru_parse_document",
    annotations={
        "title": "同步解析文档为 Markdown",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def mineru_parse_document(params: SyncParseInput) -> dict:
    """【默认优先使用】同步解析本地文档，等待完成后将 Markdown 保存到指定目录。

    这是文档解析的默认工具。除非文件明显很大（约超过 100 页）、
    或用户明确要求后台/异步处理，否则应始终优先调用本工具，
    而不是 mineru_submit_task。

    上传文件到 MinerU DocParse API，同步等待解析完成，下载 ZIP 并解压。
    适合中小文件（<100 页），大文件请使用 mineru_submit_task 异步接口。

    Args:
        params (SyncParseInput): 包含 file_path、output_dir（可选，缺省用 MINERU_OUTPUT_DIR）及所有解析选项

    Returns:
        dict:
        成功: {"success": true, "file_name": str, "zip_path": str, "zip_size": int,
                "extract_dir": str, "md_files": [str], "md_count": int}
        失败: {"success": false, "error": str}
    """
    client = get_client()

    # 文件检查
    if not os.path.isfile(params.file_path):
        return {"success": False, "error": f"文件不存在: {params.file_path}"}

    output_dir, err = _resolve_output_dir(params.output_dir)
    if err is not None:
        return err

    form_data = params.to_form_data()
    file_name = os.path.basename(params.file_path)

    try:
        response = client.sync_parse(params.file_path, form_data, response_format_zip=True)
        response.raise_for_status()
    except Exception as e:
        return _handle_client_error(e)

    # 检查是否真的拿到 ZIP
    content_type = response.headers.get("Content-Type", "")
    if "zip" not in content_type and "octet-stream" not in content_type:
        try:
            body = response.json()
            return {"success": False, "error": "API 返回了非 ZIP 响应", "detail": body}
        except Exception:
            return {"success": False, "error": f"非 ZIP 响应 (Content-Type: {content_type})"}

    result = _save_and_extract(response.content, file_name, output_dir, params.extract_zip)
    return {"success": True, "file_name": file_name, **result}


# ═══════════════════════════════════════════════════════
# 工具 2: 异步提交
# ═══════════════════════════════════════════════════════
@mcp.tool(
    name="mineru_submit_task",
    annotations={
        "title": "提交异步解析任务",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
def mineru_submit_task(params: AsyncSubmitInput) -> dict:
    """提交文档到 MinerU 异步解析队列，立即返回 task_id。

    仅在文件较大（约超过 100 页）或用户明确要求后台/异步处理时使用。
    常规文档解析请优先使用 mineru_parse_document（同步接口）。

    不等待解析完成。拿到 task_id 后，使用 mineru_get_task_status 查询进度，
    完成后用 mineru_get_task_result 下载结果。

    Args:
        params (AsyncSubmitInput): 包含 file_path 及所有解析选项

    Returns:
        dict:
        成功: {"success": true, "task_id": str, "status": str,
                "status_url": str, "result_url": str}
        失败: {"success": false, "error": str}
    """
    client = get_client()

    if not os.path.isfile(params.file_path):
        return {"success": False, "error": f"文件不存在: {params.file_path}"}

    try:
        result = client.submit_task(params.file_path, params.to_form_data())
        return {"success": True, **result}
    except Exception as e:
        return _handle_client_error(e)


# ═══════════════════════════════════════════════════════
# 工具 3: 查询任务状态
# ═══════════════════════════════════════════════════════
@mcp.tool(
    name="mineru_get_task_status",
    annotations={
        "title": "查询异步任务状态",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def mineru_get_task_status(params: TaskQueryInput) -> dict:
    """查询异步解析任务的当前状态。

    Args:
        params (TaskQueryInput): 包含 task_id

    Returns:
        dict:
        {
            "success": true,
            "task_id": str,
            "status": "queued" | "processing" | "completed" | "failed",
            "backend": str, "file_names": [str],
            "error": str|null,           # 失败时的错误信息
            "queued_tasks": int,         # 前面排队的任务数
            "processing_tasks": int,     # 正在处理的任务数
        }
    """
    client = get_client()

    try:
        status = client.task_status(params.task_id)
        return {"success": True, **status}
    except Exception as e:
        return _handle_client_error(e)


# ═══════════════════════════════════════════════════════
# 工具 4: 获取任务结果
# ═══════════════════════════════════════════════════════
@mcp.tool(
    name="mineru_get_task_result",
    annotations={
        "title": "获取异步任务结果",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def mineru_get_task_result(params: TaskResultInput) -> dict:
    """获取已完成异步任务的解析结果，保存 ZIP 并解压到指定目录。

    仅当任务状态为 completed 时才能获取结果。
    建议先调用 mineru_get_task_status 确认状态后再取结果。

    Args:
        params (TaskResultInput): 包含 task_id、output_dir（可选，缺省用 MINERU_OUTPUT_DIR）、extract_zip

    Returns:
        dict:
        成功: {"success": true, "file_name": str, "zip_path": str,
                "zip_size": int, "extract_dir": str, "md_files": [str], "md_count": int}
        失败: {"success": false, "error": str}
    """
    output_dir, err = _resolve_output_dir(params.output_dir)
    if err is not None:
        return err

    client = get_client()

    try:
        response = client.task_result(params.task_id)
        response.raise_for_status()
    except Exception as e:
        return _handle_client_error(e)

    content_type = response.headers.get("Content-Type", "")

    # 任务未完成 → 返回 JSON 状态
    if "application/json" in content_type:
        try:
            body = response.json()
            return {
                "success": False,
                "error": f"任务尚未完成或不可用（status={body.get('status', 'unknown')}）",
                "detail": body,
            }
        except Exception:
            pass

    # ZIP 结果
    if "zip" in content_type or "octet-stream" in content_type:
        # 从 status 接口获取原始文件名（可选回退）
        file_name = f"{params.task_id}.zip"
        try:
            st = client.task_status(params.task_id)
            names = st.get("file_names", [])
            if names:
                file_name = names[0]
        except Exception:
            pass

        result = _save_and_extract(
            response.content, file_name, output_dir, params.extract_zip
        )
        return {"success": True, "file_name": file_name, **result}

    return {"success": False, "error": f"未知响应格式 (Content-Type: {content_type})"}


# ═══════════════════════════════════════════════════════
# 工具 5: 健康检查
# ═══════════════════════════════════════════════════════
@mcp.tool(
    name="mineru_health_check",
    annotations={
        "title": "MinerU 服务健康检查",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
def mineru_health_check() -> dict:
    """检查 MinerU DocParse API 服务是否正常运行。

    Returns:
        dict:
        {
            "success": true,
            "status": "healthy",
            "version": "3.4.2",
            "queued_tasks": int,         # 当前排队任务数
            "processing_tasks": int,      # 当前处理中任务数
            "max_concurrent_requests": int,
        }
    """
    client = get_client()
    try:
        info = client.health()
        return {"success": True, **info}
    except Exception as e:
        return _handle_client_error(e)


# ── 入口 ───────────────────────────────────────────────
_VALID_TRANSPORTS = ("stdio", "streamable-http")


def main():
    """CLI 入口点。

    通过环境变量切换传输模式:

    stdio 模式（默认，本地子进程，适合 Claude Code / Cursor 等客户端）:
        mineru-mcp-server

    Streamable HTTP 模式（远程服务，支持多客户端连接）:
        MCP_TRANSPORT=streamable-http MCP_PORT=8001 mineru-mcp-server
    """
    transport = os.getenv("MCP_TRANSPORT", "stdio")

    if transport not in _VALID_TRANSPORTS:
        raise ValueError(
            f"不支持的 MCP_TRANSPORT: {transport!r}，仅支持 {' / '.join(_VALID_TRANSPORTS)}"
        )

    if transport == "streamable-http":
        host = os.getenv("MCP_HOST", "127.0.0.1")
        port = int(os.getenv("MCP_PORT", "8001"))
        mcp.run(transport="streamable-http", host=host, port=port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
