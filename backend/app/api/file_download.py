"""知识库文件下载：MIME 与 Content-Disposition 策略。"""

from __future__ import annotations

import mimetypes

# 浏览器可直接打开/播放的类型：默认 inline；其余 attachment。
_INLINE_PREFIXES = ("video/", "audio/", "image/", "text/")
_INLINE_TYPES = frozenset(
    {
        "application/pdf",
        "application/json",
    }
)


def media_type_for_filename(filename: str) -> str:
    name = (filename or "").strip()
    guessed, _ = mimetypes.guess_type(name)
    if guessed:
        return guessed
    if name.lower().endswith(".md"):
        return "text/markdown; charset=utf-8"
    return "application/octet-stream"


def content_disposition_type(
    media_type: str, *, force_download: bool = False
) -> str:
    if force_download:
        return "attachment"
    base = (media_type or "").split(";", 1)[0].strip().lower()
    if base in _INLINE_TYPES or any(base.startswith(p) for p in _INLINE_PREFIXES):
        return "inline"
    return "attachment"
