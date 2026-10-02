from __future__ import annotations

from typing import Literal

from app.storage.kb_text_files import is_kb_text_file

KbFileKind = Literal["doc", "text", "binary"]


def classify(rel_path: str) -> KbFileKind:
    """按 ADR 决策 4 判定知识库文件类型。"""
    path = (rel_path or "").replace("\\", "/").rstrip("/")
    name = path.rsplit("/", 1)[-1] if path else ""
    if name.lower().endswith(".md"):
        return "doc"
    if is_kb_text_file(path or name):
        return "text"
    return "binary"
