"""知识库文件下载：MIME 与 Content-Disposition 策略。"""

from __future__ import annotations

import mimetypes
from pathlib import PurePosixPath

from app.storage.kb_text_files import KB_TEXT_FILE_NAMES, TEXT_PREVIEW_SUFFIXES

# 作为文档导航打开时会执行内部脚本；`<img>` 不受影响
_FORCE_ATTACHMENT_SUFFIXES = frozenset({".svg"})


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
    media_type: str,
    *,
    force_download: bool = False,
    filename: str | None = None,
) -> str:
    """默认 inline（点击预览）；?download=1 / force_download / SVG 导航用 attachment。

    SVG 若 inline 打开会当文档执行脚本；强制 attachment 后 `<img src>` 仍可预览。
    """
    if force_download:
        return "attachment"
    if filename:
        suffix = PurePosixPath(filename.replace("\\", "/")).suffix.lower()
        if suffix in _FORCE_ATTACHMENT_SUFFIXES:
            return "attachment"
    return "inline"
