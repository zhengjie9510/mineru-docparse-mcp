"""MinerU MCP Server — 同步文档解析 + 健康检查。"""

import os
from datetime import datetime, timezone

import requests
from fastmcp import FastMCP

from .client import get_client
from .models import ParseDocumentInput

# ── 服务 ──
mcp = FastMCP("mineru_mcp")


# ── 工具函数 ──
def _get_output_dir() -> tuple[str | None, dict | None]:
    """读取 MINERU_OUTPUT_DIR 环境变量，相对路径以 cwd 为基准解析。"""
    output_dir = os.getenv("MINERU_OUTPUT_DIR")
    if not output_dir:
        return None, {
            "success": False,
            "error": "服务未配置 MINERU_OUTPUT_DIR 环境变量，无法确定文件保存位置。"
            "请在启动 mineru-docparse-mcp 时设置该环境变量后重试",
        }
    if not os.path.isabs(output_dir):
        output_dir = os.path.normpath(os.path.join(os.getcwd(), output_dir))
    return output_dir, None


def _save_response(content: bytes, content_type: str, base_name: str, output_dir: str) -> dict:
    """原样保存响应到磁盘。根据 Content-Type 自动选择 .zip 或 .json。"""
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
        return {"success": False, "error": "请求超时，文件可能过大，请尝试调整解析参数（如缩小页面范围）"}
    if isinstance(e, requests.HTTPError):
        return {
            "success": False,
            "error": f"API 返回 HTTP {e.response.status_code}",
            "detail": e.response.text[:500],
        }
    if isinstance(e, requests.RequestException):
        return {"success": False, "error": f"网络请求失败: {e}"}
    return {"success": False, "error": f"未知错误: {e}"}


# ── 同步解析 ──
@mcp.tool()
def mineru_parse_document(params: ParseDocumentInput) -> dict:
    """将 PDF · DOCX · PPTX · XLSX · 图片 · 网页转为结构化 Markdown / JSON

    上传文件到 MinerU DocParse API 进行内容提取
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


# ── 健康检查 ──
@mcp.tool()
def mineru_health_check() -> dict:
    """检查 MinerU DocParse API 服务是否正常运行。"""
    client = get_client()
    try:
        info = client.health()
        return {"success": True, **info}
    except Exception as e:
        return _handle_client_error(e)


def main():
    """CLI 入口。MCP_TRANSPORT=streamable-http 启用 HTTP 模式，默认 stdio。"""
    transport = os.getenv("MCP_TRANSPORT", "stdio")

    if transport == "streamable-http":
        host = os.getenv("MCP_HOST", "127.0.0.1")
        port = int(os.getenv("MCP_PORT", "8001"))
        mcp.run(transport="streamable-http", host=host, port=port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
