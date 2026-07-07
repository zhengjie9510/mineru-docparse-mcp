"""Pydantic 输入模型，字段与 MinerU DocParse OpenAPI schema 保持一致。"""

import os
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ── 枚举 ──
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


def _resolve_file_path(v: str) -> str:
    """将 file_path 解析为绝对路径。相对路径以当前工作目录为基准。"""
    if os.path.isabs(v):
        return v
    return os.path.normpath(os.path.join(os.getcwd(), v))


def _check_page_range(model):
    if model.end_page_id < model.start_page_id:
        raise ValueError(
            f"end_page_id ({model.end_page_id}) 不能小于 start_page_id ({model.start_page_id})"
        )
    return model


def _to_form_data(model) -> dict:
    """把解析参数转为 multipart/form-data 字段（值统一为字符串或字符串列表）。"""
    data: dict = {
        "lang_list": [lang.value for lang in model.lang_list],
        "backend": model.backend.value,
        "effort": model.effort.value,
        "parse_method": model.parse_method.value,
        "formula_enable": str(model.formula_enable).lower(),
        "table_enable": str(model.table_enable).lower(),
        "image_analysis": str(model.image_analysis).lower(),
        "return_md": str(model.return_md).lower(),
        "return_middle_json": str(model.return_middle_json).lower(),
        "return_model_output": str(model.return_model_output).lower(),
        "return_content_list": str(model.return_content_list).lower(),
        "return_images": str(model.return_images).lower(),
        "response_format_zip": str(model.response_format_zip).lower(),
        "return_original_file": str(model.return_original_file).lower(),
        "client_side_output_generation": str(model.client_side_output_generation).lower(),
        "start_page_id": str(model.start_page_id),
        "end_page_id": str(model.end_page_id),
    }
    if model.server_url is not None:
        data["server_url"] = model.server_url
    return data


# ── POST /file_parse ──
class ParseDocumentInput(BaseModel):
    """mineru_parse_document 的输入参数，对应官方 POST /file_parse 接口。

    字段及默认值与官方 OpenAPI schema 一致，仅 response_format_zip 默认改为 True。
    """
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    file_path: str = Field(
        ...,
        min_length=1,
        description="本地文档路径，支持绝对路径和相对路径（相对路径以当前工作目录为基准）",
    )
    lang_list: list[Lang] = Field(
        default=[Lang.CH],
        description="OCR 语言列表，仅 pipeline 后端生效。默认 ['ch']（中文，含中英日繁拉丁）",
    )
    backend: Backend = Field(
        default=Backend.HYBRID_ENGINE,
        description="解析后端，默认 hybrid-engine（本地混合解析）",
    )
    effort: Effort = Field(
        default=Effort.MEDIUM,
        description="仅 hybrid 后端生效的解析精度，默认 medium（更快，不含图表分析）",
    )
    parse_method: ParseMethod = Field(
        default=ParseMethod.AUTO,
        description="仅 pipeline/hybrid 后端生效的 PDF 解析方式，默认 auto（自动判断）",
    )
    formula_enable: bool = Field(default=True, description="启用公式解析（LaTeX），默认 True")
    table_enable: bool = Field(default=True, description="启用表格解析，默认 True")
    image_analysis: bool = Field(
        default=True, description="启用图片/图表分析（VLM/hybrid 后端生效），默认 True"
    )
    server_url: str | None = Field(
        default=None,
        description="仅 *-http-client 后端需要，OpenAI 兼容服务器地址，如 http://127.0.0.1:30000。默认不设置",
    )
    return_md: bool = Field(default=True, description="响应中返回 Markdown 内容，默认 True")
    return_middle_json: bool = Field(
        default=False, description="响应中返回中间态 JSON，默认 False"
    )
    return_model_output: bool = Field(
        default=False, description="响应中返回模型原始输出 JSON，默认 False"
    )
    return_content_list: bool = Field(
        default=False, description="响应中返回内容列表 JSON，默认 False"
    )
    return_images: bool = Field(default=True, description="响应中返回提取出的图片，默认 False")
    response_format_zip: bool = Field(
        default=True,
        description="以 ZIP 文件形式返回结果（而非 JSON）。"
        "官方接口默认为 False，本项目默认改为 True，因为结果按文件落盘更符合本项目定位",
    )
    return_original_file: bool = Field(
        default=False,
        description="ZIP 结果中包含处理后的原始文件；仅 response_format_zip=true 时生效，默认 False",
    )
    client_side_output_generation: bool = Field(
        default=False,
        description="将最终 Markdown/内容列表的生成推迟到客户端处理，默认 False",
    )
    start_page_id: int = Field(default=0, ge=0, description="起始页码，从 0 开始，默认 0")
    end_page_id: int = Field(default=99999, ge=0, description="结束页码，从 0 开始，默认 99999")

    _validate_page_range = model_validator(mode="after")(_check_page_range)

    @field_validator("file_path")
    @classmethod
    def _resolve_file_path_validator(cls, v: str) -> str:
        return _resolve_file_path(v)

    def to_form_data(self) -> dict:
        return _to_form_data(self)

