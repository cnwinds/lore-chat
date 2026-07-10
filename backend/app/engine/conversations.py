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
    def _assistant_content(msg: dict) -> str:
        if msg.get("text"):
            return str(msg["text"]).strip()
        parts: list[str] = []
        for block in msg.get("timeline") or []:
            if block.get("type") == "text" and block.get("content"):
                part = str(block["content"]).strip()
                if part:
                    parts.append(part)
        return "\n\n".join(parts)

    @classmethod
    def llm_history(
        cls,
        conv: dict,
        *,
        max_turns: int = 20,
        max_chars: int = 32000,
    ) -> list[dict]:
        """将已保存的对话转为 LLM 多轮 messages（不含本轮尚未保存的用户消息）。"""
        candidates: list[dict] = []
        for msg in conv.get("messages", []):
            role = msg.get("role")
            if role == "user":
                text = (msg.get("text") or "").strip()
                if text:
                    candidates.append({"role": "user", "content": text})
            elif role == "assistant":
                text = cls._assistant_content(msg)
                if text:
                    candidates.append({"role": "assistant", "content": text})

        user_indices = [i for i, m in enumerate(candidates) if m["role"] == "user"]
        if len(user_indices) > max_turns:
            candidates = candidates[user_indices[-max_turns] :]

        while candidates:
            total = sum(len(m["content"]) for m in candidates)
            if total <= max_chars:
                break
            candidates.pop(0)
        return candidates

    @staticmethod
    def context_excerpt(conv: dict, *, max_chars: int = 4000) -> str:
        lines: list[str] = []
        for msg in conv.get("messages", [])[-8:]:
            role = msg.get("role")
            if role == "user" and msg.get("text"):
                lines.append(f"用户：{msg['text']}")
            elif role == "assistant":
                text = ConversationStore._assistant_content(msg)
                if text:
                    lines.append(f"助手：{text[:800]}")
                elif msg.get("timeline"):
                    for block in msg["timeline"]:
                        if block.get("type") == "tool" and block.get("tool") == "ask_user":
                            q = block.get("question") or block.get("summary") or ""
                            if q:
                                lines.append(f"助手征询：{q}")
        text = "\n".join(lines)
        return text[:max_chars] if len(text) > max_chars else text
