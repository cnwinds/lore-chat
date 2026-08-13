"""知识库文本类非 Markdown 文件：扩展名白名单（与下载预览对齐）。"""

from __future__ import annotations

from pathlib import PurePosixPath

# 浏览器预览友好的文本后缀；Markdown 由 write_doc / read_doc 文档路径单独处理。
KB_TEXT_FILE_SUFFIXES: frozenset[str] = frozenset(
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
        ".txt",
        ".log",
        ".env",
        ".gitignore",
        ".dockerfile",
    }
)

KB_TEXT_FILE_NAMES: frozenset[str] = frozenset(
    {
        "dockerfile",
        "makefile",
        "license",
        "readme",
    }
)

# 下载预览含 .md；写入工具白名单不含 .md。
TEXT_PREVIEW_SUFFIXES: frozenset[str] = KB_TEXT_FILE_SUFFIXES | {".md"}


def is_kb_text_file(path_or_name: str) -> bool:
    """是否允许作为 write_kb_file / 纯文本 read_doc 的目标（排除 .md）。"""
    name = PurePosixPath((path_or_name or "").replace("\\", "/")).name.strip()
    if not name or name.lower().endswith(".md"):
        return False
    suffix = PurePosixPath(name).suffix.lower()
    if suffix in KB_TEXT_FILE_SUFFIXES:
        return True
    return name.lower() in KB_TEXT_FILE_NAMES
