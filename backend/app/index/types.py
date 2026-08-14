from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class Hit:
    doc_id: str
    chunk: str
    score: float
    source: str
    # 会话消息级命中（ConversationFTS 桥接）才会填充；KB 命中保持 None。
    message_id: str | None = None
    start_char: int | None = None
    end_char: int | None = None
    offset_version: str | None = None
    role: str | None = None
    ts: str | None = None
    conversation_title: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """供 tool 结果 / SSE 等 JSON 序列化。"""
        return asdict(self)
