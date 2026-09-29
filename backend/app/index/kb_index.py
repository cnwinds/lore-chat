"""文档库在分区检索底座上的常量与路径规范化。"""

from __future__ import annotations

KB_FAMILY = "kb"
KB_PARTITION = "kb:main"


def normalize_kb_path(doc_id: str) -> str:
    return doc_id.replace("\\", "/").lstrip("/")
