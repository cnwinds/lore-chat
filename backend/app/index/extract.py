from pathlib import Path

_PLAIN = {".md", ".txt", ".markdown"}
_READABLE = {".pdf", ".docx", ".pptx", ".xlsx", ".doc", ".ppt", ".xls", ".html", ".htm", ".csv"}


def extract_text(path: str | Path) -> str:
    path = Path(path)
    ext = path.suffix.lower()
    if ext in _PLAIN:
        return path.read_text(encoding="utf-8", errors="ignore")
    if ext in _READABLE:
        try:
            from markitdown import MarkItDown
            from markitdown._markitdown import FileConversionException

            md = MarkItDown()
            result = md.convert(str(path))
            return result.text_content or ""
        except (Exception, FileConversionException):
            return ""
    # 二进制（zip/rar 等）不抽取内容
    return ""
