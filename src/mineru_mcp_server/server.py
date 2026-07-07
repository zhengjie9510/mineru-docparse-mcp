"""MinerU MCP Server — 5 个工具覆盖 DocParse API 全部端点。

保存路径不是接口参数：所有结果统一存到 MINERU_OUTPUT_DIR 环境变量指定的目录，
这是 server 启动时的固定配置。MinerU 返回什么格式就原样存成什么格式（.zip 或 .json），
本项目不做解压或内容解析。
"""

import os
from datetime import datetime, timezone

import requests
from fastmcp import FastMCP

from .client import get_client
from .models import (
    ParseDocumentInput,
    SubmitTaskInput,
    TaskResultInput,
    TaskStatusInput,
)

# ── 服务 ───────────────────────────────────────────────
mcp = FastMCP("mineru_mcp")


# ── 工具函数 ───────────────────────────────────────────
def _get_output_dir() -> tuple[str | None, dict | None]:
    """从 MINERU_OUTPUT_DIR 环境变量读取输出目录。这是 server 级配置，不是接口参数。

    Returns:
        (output_dir, error) — 成功时 error 为 None；未配置或配置不合法时 output_dir 为 None。
    """
    output_dir = os.getenv("MINERU_OUTPUT_DIR")
    if not output_dir:
        return None, {
            "success": False,
            "error": "服务未配置 MINERU_OUTPUT_DIR 环境变量，无法确定文件保存位置。"
            "请在启动 mineru-docparse-mcp 时设置该环境变量后重试",
        }
    if not os.path.isabs(output_dir):
        return None, {
            "success": False,
            "error": f"MINERU_OUTPUT_DIR 必须是绝对路径: {output_dir}",
        }
    return output_dir, None


def _save_response(content: bytes, content_type: str, base_name: str, output_dir: str) -> dict:
    """把 MinerU 的响应原样存到磁盘，不解压、不解析内容。

    存成 .zip 还是 .json 完全由响应的 Content-Type 决定：
    - zip / octet-stream → 原样存为 .zip
    - json → 原样存为 .json（其中可能包含 md_content 等字段，取决于调用时的 return_* 参数）

    Returns:
        {"saved_path": str, "file_size": int, "format": "zip"|"json"}
    """
    os.makedirs(output_dir, exist_ok=True)

    if "json" in content_type:
        ext, fmt = ".json", "json"
    else:
        ext, fmt = ".zip", "zip"

    saved_path = os.path.join(output_dir, f"{base_name}{ext}")
    # 同名文件已存在时加时间戳，避免覆盖历史结果
    if os.path.exists(saved_path):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        saved_path = os.path.join(output_dir, f"{base_name}_{stamp}{ext}")

    with open(saved_path, "wb") as f:
        f.write(content)

    return {"saved_path": saved_path, "file_size": len(content), "format": fmt}


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
def mineru_parse_document(params: ParseDocumentInput) -> dict:
    """【默认优先使用】同步解析本地文档，等待完成后将结果保存到磁盘。

    这是文档解析的默认工具。除非文件明显很大（约超过 100 页）、
    或用户明确要求后台/异步处理，否则应始终优先调用本工具，
    而不是 mineru_submit_task。

    上传文件到 MinerU DocParse API，同步等待解析完成。返回内容原样保存：
    response_format_zip=true（默认）时存为 .zip，为 false 时存为 .json，不做解压或内容解析。
    适合中小文件（<100 页），大文件请使用 mineru_submit_task 异步接口。

    结果保存目录由服务端 MINERU_OUTPUT_DIR 环境变量决定，不是本工具的参数。

    Args:
        params (ParseDocumentInput): 见 ParseDocumentInput 各字段说明

    Returns:
        dict:
        成功: {"success": true, "file_name": str, "saved_path": str, "file_size": int, "format": "zip"|"json"}
        失败: {"success": false, "error": str}
    """
    if not os.path.isfile(params.file_path):
        return {"success": False, "error": f"文件不存在: {params.file_path}"}

    output_dir, err = _get_output_dir()
    if err is not None:
        return err

    client = get_client()
    form_data = params.to_form_data()
    file_name = os.path.basename(params.file_path)
    base_name = os.path.splitext(file_name)[0]

    try:
        response = client.sync_parse(params.file_path, form_data)
        response.raise_for_status()
    except Exception as e:
        return _handle_client_error(e)

    content_type = response.headers.get("Content-Type", "")
    result = _save_response(response.content, content_type, base_name, output_dir)
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
def mineru_submit_task(params: SubmitTaskInput) -> dict:
    """提交文档到 MinerU 异步解析队列，立即返回 task_id。

    仅在文件较大（约超过 100 页）或用户明确要求后台/异步处理时使用。
    常规文档解析请优先使用 mineru_parse_document（同步接口）。

    不等待解析完成。拿到 task_id 后，使用 mineru_get_task_status 查询进度，
    完成后用 mineru_get_task_result 下载结果。

    Args:
        params (SubmitTaskInput): 见 SubmitTaskInput 各字段说明

    Returns:
        dict:
        成功: {"success": true, "task_id": str, "status": str,
                "status_url": str, "result_url": str}
        失败: {"success": false, "error": str}
    """
    if not os.path.isfile(params.file_path):
        return {"success": False, "error": f"文件不存在: {params.file_path}"}

    client = get_client()
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
def mineru_get_task_status(params: TaskStatusInput) -> dict:
    """查询异步解析任务的当前状态。

    Args:
        params (TaskStatusInput): 包含 task_id

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
    """获取已完成异步任务的解析结果，原样保存到磁盘。

    仅当任务状态为 completed 时才能获取结果。
    建议先调用 mineru_get_task_status 确认状态后再取结果。

    返回内容原样保存，不做解压或内容解析（是 .zip 还是 .json 取决于
    提交任务时 response_format_zip 参数的取值）。
    结果保存目录由服务端 MINERU_OUTPUT_DIR 环境变量决定，不是本工具的参数。

    Args:
        params (TaskResultInput): 包含 task_id

    Returns:
        dict:
        成功: {"success": true, "file_name": str, "saved_path": str, "file_size": int, "format": "zip"|"json"}
        失败: {"success": false, "error": str}
    """
    output_dir, err = _get_output_dir()
    if err is not None:
        return err

    client = get_client()
    try:
        response = client.task_result(params.task_id)
        response.raise_for_status()
    except Exception as e:
        return _handle_client_error(e)

    content_type = response.headers.get("Content-Type", "")

    file_name = f"{params.task_id}"
    try:
        st = client.task_status(params.task_id)
        names = st.get("file_names", [])
        if names:
            file_name = os.path.splitext(names[0])[0]
    except Exception:
        pass

    result = _save_response(response.content, content_type, file_name, output_dir)
    return {"success": True, "file_name": file_name, **result}


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
        mineru-docparse-mcp

    Streamable HTTP 模式（远程服务，支持多客户端连接）:
        MCP_TRANSPORT=streamable-http MCP_PORT=8001 mineru-docparse-mcp
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
