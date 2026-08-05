from __future__ import annotations

import json
import uuid


def now_iso() -> str:
    from app.time import now_iso_seconds

    return now_iso_seconds()


def new_id() -> str:
    return uuid.uuid4().hex


def title_from_text(text: str) -> str:
    line = text.strip().split("\n")[0]
    if len(line) > 40:
        return line[:40] + "…"
    return line or "新对话"


def loads_json(raw: str | None, default):
    if not raw:
        return default
    return json.loads(raw)


def dumps_json(value) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


class TurnInProgress(Exception):
    """本会话已存在一个 running turn，同一 client_message_id 不应再次触发 Agent。"""

    def __init__(self, turn_id: str, retry_after_ms: int = 1000):
        super().__init__(f"turn {turn_id} in progress")
        self.turn_id = turn_id
        self.retry_after_ms = retry_after_ms
