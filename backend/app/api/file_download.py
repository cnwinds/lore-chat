"""知识库文件下载：MIME 与 Content-Disposition 策略。"""

from __future__ import annotations

import mimetypes
from pathlib import PurePosixPath

from app.storage.kb_text_files import KB_TEXT_FILE_NAMES, TEXT_PREVIEW_SUFFIXES

# 作为文档 / object / embed 打开时会执行内部脚本；`<img>` 不受影响
_FORCE_ATTACHMENT_SUFFIXES = frozenset({".svg"})

# 这些 Sec-Fetch-Dest 下 SVG 可当文档执行脚本 → 强制 attachment
_SVG_UNSAFE_FETCH_DEST = frozenset(
    {"document", "iframe", "frame", "embed", "object"}
)


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
    sec_fetch_dest: str | None = None,
) -> str:
    """默认 inline；?download=1 强制 attachment。

    SVG：仅在顶层导航 / iframe / embed / object 时用 attachment 防 XSS；
    `<img>`（Sec-Fetch-Dest: image）及其它子资源用 inline，否则部分浏览器无法预览。
    """
    if force_download:
        return "attachment"
    if filename:
        suffix = PurePosixPath(filename.replace("\\", "/")).suffix.lower()
        if suffix in _FORCE_ATTACHMENT_SUFFIXES:
            dest = (sec_fetch_dest or "").strip().lower()
            if dest in _SVG_UNSAFE_FETCH_DEST:
                return "attachment"
            return "inline"
    return "inline"
