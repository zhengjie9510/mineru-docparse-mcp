"""MinerU DocParse API HTTP 客户端。"""

import os

import requests


class MinerUClient:
    """MinerU DocParse API HTTP 客户端。"""

    def __init__(self, base_url: str | None = None, timeout: int | None = None):
        self.base_url = (base_url or os.getenv("MINERU_API_URL", "http://localhost:8000")).rstrip("/")
        self.timeout = timeout or int(os.getenv("MINERU_API_TIMEOUT", "600"))

    def health(self) -> dict:
        """GET /health"""
        r = requests.get(f"{self.base_url}/health", timeout=10)
        r.raise_for_status()
        return r.json()

    def sync_parse(self, file_path: str, form_data: dict) -> requests.Response:
        """POST /file_parse — 上传文件，同步等待解析完成。"""
        filename = os.path.basename(file_path)
        with open(file_path, "rb") as f:
            return requests.post(
                f"{self.base_url}/file_parse",
                files={"files": (filename, f)},
                data=form_data,
                timeout=self.timeout,
            )


_client: MinerUClient | None = None


def get_client() -> MinerUClient:
    """获取全局单例客户端，首次调用时从环境变量读取配置。"""
    global _client
    if _client is None:
        _client = MinerUClient()
    return _client
