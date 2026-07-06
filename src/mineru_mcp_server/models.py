"""Pydantic 输入模型 — 所有 MCP 工具的参数校验。"""

import os
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ── 枚举 ───────────────────────────────────────────────
class Backend(str, Enum):
    """解析后端"""
    PIPELINE = "pipeline"
    VLM_ENGINE = "vlm-engine"
    HYBRID_ENGINE = "hybrid-engine"
    VLM_HTTP_CLIENT = "vlm-http-client"
    HYBRID_HTTP_CLIENT = "hybrid-http-client"


class ParseMethod(str, Enum):
    """PDF 解析方式"""
    AUTO = "auto"
    TXT = "txt"
    OCR = "ocr"


class Lang(str, Enum):
    """OCR 识别语言"""
    CH = "ch"
    CH_SERVER = "ch_server"
    KOREAN = "korean"
    TA = "ta"
    TE = "te"
    KA = "ka"
    TH = "th"
    EL = "el"
    ARABIC = "arabic"
    EAST_SLAVIC = "east_slavic"
    CYRILLIC = "cyrillic"
    DEVANAGARI = "devanagari"


class Effort(str, Enum):
    """Hybrid 后端解析精度"""
    MEDIUM = "medium"
    HIGH = "high"


# ── 共享解析参数 Mixin ─────────────────────────────────
class ParseOptions(BaseModel):
    """文档解析的通用参数（同步和异步共用）。"""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    backend: Backend = Field(
        default=Backend.PIPELINE,
        description="解析后端: pipeline(通用无幻觉) / vlm-engine(本地VLM) / hybrid-engine(本地混合,推荐) / vlm-http-client(远程VLM) / hybrid-http-client(远程混合)",
    )
    lang: Lang = Field(
        default=Lang.CH,
        description="OCR 语言，中文文档选 ch（含中英日繁拉丁）",
    )
    parse_method: ParseMethod = Field(
        default=ParseMethod.AUTO,
        description="PDF 解析方式: auto(自动) / txt(文本提取) / ocr(OCR识别)",
    )
    effort: Effort = Field(
        default=Effort.MEDIUM,
        description="Hybrid 后端专用: medium(快速,无图表分析) / high(高精度,含图表分析)",
    )
    formula_enable: bool = Field(
        default=True, description="启用公式解析（LaTeX 格式）"
    )
    table_enable: bool = Field(
        default=True, description="启用表格解析"
    )
    image_analysis: bool = Field(
        default=True, description="启用图片/图表分析（VLM/Hybrid 后端有效）"
    )
    start_page: int = Field(
        default=0, ge=0, description="起始页码，从 0 开始"
    )
    end_page: int = Field(
        default=99999, ge=0, description="结束页码，从 0 开始"
    )
    server_url: Optional[str] = Field(
        default=None,
        description="(仅 http-client 后端) OpenAI 兼容服务器地址，如 http://127.0.0.1:30000",
    )

    @model_validator(mode="after")
    def _check_page_range(self):
        if self.end_page < self.start_page:
            raise ValueError(
                f"end_page ({self.end_page}) 不能小于 start_page ({self.start_page})"
            )
        return self

    def to_form_data(self) -> dict:
        """转为 multipart/form-data 字段（值统一为字符串或字符串列表）。"""
        data: dict = {
            "backend": self.backend.value,
            "lang_list": [self.lang.value],
            "parse_method": self.parse_method.value,
            "effort": self.effort.value,
            "formula_enable": str(self.formula_enable).lower(),
            "table_enable": str(self.table_enable).lower(),
            "image_analysis": str(self.image_analysis).lower(),
            "start_page_id": str(self.start_page),
            "end_page_id": str(self.end_page),
        }
        if self.server_url is not None:
            data["server_url"] = self.server_url
        return data


def _validate_absolute_path(v: str) -> str:
    if not os.path.isabs(v):
        raise ValueError(f"必须使用绝对路径: {v}")
    return v


# ── 同步解析 ───────────────────────────────────────────
class SyncParseInput(ParseOptions):
    """POST /file_parse — 同步解析，等待完成后直接返回结果。"""
    file_path: str = Field(
        ..., min_length=1, description="本地文档绝对路径（.docx/.pdf/.pptx/.xlsx）"
    )
    output_dir: Optional[str] = Field(
        default=None,
        description="输出目录绝对路径，ZIP 和 Markdown 保存于此。"
        "不填则使用 MINERU_OUTPUT_DIR 环境变量指定的默认目录",
    )
    extract_zip: bool = Field(
        default=True, description="是否自动解压 ZIP 到输出目录下的同名文件夹"
    )

    @field_validator("file_path")
    @classmethod
    def _validate_file_path(cls, v: str) -> str:
        return _validate_absolute_path(v)

    @field_validator("output_dir")
    @classmethod
    def _validate_output_dir(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_absolute_path(v)


# ── 异步提交 ───────────────────────────────────────────
class AsyncSubmitInput(ParseOptions):
    """POST /tasks — 提交异步解析任务，立即返回 task_id。"""
    file_path: str = Field(
        ..., min_length=1, description="本地文档绝对路径（.docx/.pdf/.pptx/.xlsx）"
    )

    _validate_paths = field_validator("file_path")(_validate_absolute_path)


# ── 异步状态 & 结果查询 ────────────────────────────────
class TaskQueryInput(BaseModel):
    """GET /tasks/{task_id} 或 /tasks/{task_id}/result"""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    task_id: str = Field(
        ..., min_length=1, description="异步任务 ID（由 submit 接口返回）"
    )


class TaskResultInput(TaskQueryInput):
    """GET /tasks/{task_id}/result — 获取结果并保存"""
    output_dir: Optional[str] = Field(
        default=None,
        description="输出目录绝对路径，ZIP 和 Markdown 保存于此。"
        "不填则使用 MINERU_OUTPUT_DIR 环境变量指定的默认目录",
    )
    extract_zip: bool = Field(
        default=True, description="是否自动解压 ZIP"
    )

    @field_validator("output_dir")
    @classmethod
    def _validate_output_dir(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _validate_absolute_path(v)
