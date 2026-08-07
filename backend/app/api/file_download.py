"""知识库文件下载：MIME 与 Content-Disposition 策略。"""

from __future__ import annotations

import mimetypes
from pathlib import PurePosixPath

from app.storage.kb_text_files import KB_TEXT_FILE_NAMES, TEXT_PREVIEW_SUFFIXES


def media_type_for_filename(filename: str) -> str:
    name = (filename or "").strip()
    suffix = PurePosixPath(name.replace("\\", "/")).suffix.lower()
    if suffix in TEXT_PREVIEW_SUFFIXES or name.lower() in KB_TEXT_FILE_NAMES:
        if suffix == ".md":
            return "text/markdown; charset=utf-8"
        if suffix in (".html", ".htm"):
            return "text/html; charset=utf-8"
        if suffix == ".css":
            return "text/css; charset=utf-8"
        if suffix == ".json":
            return "application/json"
        return "text/plain; charset=utf-8"
    guessed, _ = mimetypes.guess_type(name)
    if guessed:
        return guessed
    return "application/octet-stream"


def content_disposition_type(
    media_type: str, *, force_download: bool = False
) -> str:
    """默认 inline（点击预览）；仅 ?download=1 / force_download 才 attachment。"""
    if force_download:
        return "attachment"
    return "inline"
