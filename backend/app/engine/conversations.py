from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _title_from_text(text: str) -> str:
    line = text.strip().split("\n")[0]
    if len(line) > 40:
        return line[:40] + "…"
    return line or "新对话"


class ConversationStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({})

    def _read(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def create(self, title: str | None = None) -> str:
        data = self._read()
        cid = uuid.uuid4().hex[:12]
        stamp = _now()
        data[cid] = {
            "id": cid,
            "title": title or "新对话",
            "created_at": stamp,
            "updated_at": stamp,
            "messages": [],
        }
        self._write(data)
        return cid

    def get(self, cid: str) -> dict:
        conv = self._read().get(cid)
        if conv is None:
            raise KeyError(cid)
        return conv

    def list_all(self) -> list[dict]:
        items = []
        for conv in self._read().values():
            items.append(
                {
                    "id": conv["id"],
                    "title": conv["title"],
                    "created_at": conv["created_at"],
                    "updated_at": conv["updated_at"],
                    "message_count": len(conv.get("messages", [])),
                }
            )
        return sorted(items, key=lambda c: c["updated_at"], reverse=True)

    def append_exchange(
        self,
        cid: str,
        user_text: str,
        assistant_msg: dict,
        user_ts: str | None = None,
    ) -> dict:
        data = self._read()
        conv = data.get(cid)
        if conv is None:
            raise KeyError(cid)

        user_msg = {"role": "user", "text": user_text, "ts": user_ts or _now()}
        conv["messages"].append(user_msg)
        conv["messages"].append(assistant_msg)
        conv["updated_at"] = _now()
        if conv["title"] == "新对话" and user_text.strip():
            conv["title"] = _title_from_text(user_text)
        data[cid] = conv
        self._write(data)
        return conv

    def append_messages(self, cid: str, messages: list[dict]) -> dict:
        data = self._read()
        conv = data.get(cid)
        if conv is None:
            raise KeyError(cid)

        conv["messages"].extend(messages)
        conv["updated_at"] = _now()
        data[cid] = conv
        self._write(data)
        return conv

    def delete(self, cid: str) -> None:
        data = self._read()
        if cid not in data:
            raise KeyError(cid)
        del data[cid]
        self._write(data)

    @staticmethod
    def context_excerpt(conv: dict, *, max_chars: int = 4000) -> str:
        lines: list[str] = []
        for msg in conv.get("messages", [])[-8:]:
            role = msg.get("role")
            if role == "user" and msg.get("text"):
                lines.append(f"用户：{msg['text']}")
            elif role == "assistant":
                if msg.get("text"):
                    lines.append(f"助手：{msg['text']}")
                elif msg.get("timeline"):
                    for block in msg["timeline"]:
                        if block.get("type") == "text" and block.get("content"):
                            lines.append(f"助手：{block['content'][:800]}")
                        elif block.get("type") == "tool" and block.get("tool") == "ask_user":
                            q = block.get("question") or block.get("summary") or ""
                            if q:
                                lines.append(f"助手征询：{q}")
        text = "\n".join(lines)
        return text[:max_chars] if len(text) > max_chars else text
