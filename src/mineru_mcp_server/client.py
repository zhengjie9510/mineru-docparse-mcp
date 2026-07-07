"""MinerU DocParse API 客户端 — 封装 HTTP 请求。"""

import os

import requests


class MinerUClient:
    """MinerU DocParse API 的轻量 HTTP 客户端。"""

    def __init__(self, base_url: str | None = None, timeout: int | None = None):
        self.base_url = (base_url or os.getenv("MINERU_API_URL", "http://localhost:8000")).rstrip("/")
        self.timeout = timeout or int(os.getenv("MINERU_API_TIMEOUT", "600"))

    # ── 健康检查 ──────────────────────────────────────
    def health(self) -> dict:
        """GET /health"""
        r = requests.get(f"{self.base_url}/health", timeout=10)
        r.raise_for_status()
        return r.json()

    # ── 同步解析 ──────────────────────────────────────
    def sync_parse(self, file_path: str, form_data: dict) -> requests.Response:
        """POST /file_parse — 上传文件并同步等待解析结果。

        Args:
            file_path: 本地文件路径
            form_data: 已序列化的表单字段（来自 ParseDocumentInput.to_form_data()，
                已包含 return_md / response_format_zip 等所有参数）

        Returns:
            requests.Response — 200 时 body 为 ZIP 或 JSON，取决于 form_data 里的 response_format_zip
        """
        filename = os.path.basename(file_path)
        with open(file_path, "rb") as f:
            return requests.post(
                f"{self.base_url}/file_parse",
                files={"files": (filename, f)},
                data=form_data,
                timeout=self.timeout,
            )


# ── 单例 ──────────────────────────────────────────────
_client: MinerUClient | None = None


def get_client() -> MinerUClient:
    """获取全局单例客户端。base_url/timeout 在首次调用时从环境变量读取。"""
    global _client
    if _client is None:
        _client = MinerUClient()
    return _client
