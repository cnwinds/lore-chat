"""知识库文件下载：MIME 与 Content-Disposition 策略。"""

from __future__ import annotations

import mimetypes
from pathlib import PurePosixPath

# 浏览器对 application/x-sh 等常直接下载；映射为 text/plain 便于默认预览。
_TEXT_PREVIEW_SUFFIXES = frozenset(
    {
        ".sh",
        ".bash",
        ".zsh",
        ".fish",
        ".ps1",
        ".bat",
        ".cmd",
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
        ".cfg",
        ".conf",
        ".csv",
        ".tsv",
        ".sql",
        ".xml",
        ".html",
        ".css",
        ".rs",
        ".go",
        ".java",
        ".c",
        ".h",
        ".cpp",
        ".hpp",
        ".md",
        ".txt",
        ".log",
        ".env",
        ".gitignore",
        ".dockerfile",
    }
)


def media_type_for_filename(filename: str) -> str:
    name = (filename or "").strip()
    suffix = PurePosixPath(name.replace("\\", "/")).suffix.lower()
    if suffix in _TEXT_PREVIEW_SUFFIXES or name.lower() in (
        "dockerfile",
        "makefile",
        "license",
        "readme",
    ):
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
