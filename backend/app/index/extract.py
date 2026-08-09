from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

_PLAIN = {".md", ".txt", ".markdown"}
_READABLE = {".pdf", ".docx", ".pptx", ".xlsx", ".doc", ".ppt", ".xls", ".html", ".htm", ".csv"}


@dataclass(frozen=True)
class BytesExtractResult:
    """内存字节抽取结果：区分「转换失败」与「成功但无文本」。"""

    text: str = ""
    error: str | None = None


def _normalize_ext(file_extension: str) -> str:
    ext = file_extension.lower()
    return ext if ext.startswith(".") else f".{ext}"


def _markitdown_convert(convert) -> BytesExtractResult:
    """调用 markitdown；FileConversionException 非 Exception 子类，需单独捕获。"""
    try:
        from markitdown import MarkItDown

        result = convert(MarkItDown())
        return BytesExtractResult(text=(result.text_content or "").strip())
    except Exception as e:
        return BytesExtractResult(error=f"文档转换失败: {e}")
    except BaseException as e:
        if type(e).__name__ == "FileConversionException":
            return BytesExtractResult(error=f"文档转换失败: {e}")
        raise


def extract_text(path: str | Path) -> str:
    path = Path(path)
    ext = path.suffix.lower()
    if ext in _PLAIN:
        return path.read_text(encoding="utf-8", errors="ignore")
    if ext in _READABLE:
        return _markitdown_convert(lambda md: md.convert(str(path))).text
    # 二进制（zip/rar 等）不抽取内容
    return ""


def extract_text_from_bytes(data: bytes, *, file_extension: str) -> BytesExtractResult:
    """从内存字节抽取可读文档文本（供 fetch_url 等无本地落盘场景）。"""
    ext = _normalize_ext(file_extension)
    if ext in _PLAIN:
        return BytesExtractResult(text=data.decode("utf-8", errors="ignore"))
    if ext not in _READABLE:
        return BytesExtractResult(error=f"不支持的文件类型: {ext}")
    return _markitdown_convert(
        lambda md: md.convert_stream(BytesIO(data), file_extension=ext)
    )
