from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _date_from_iso(iso: str) -> str:
    if not iso:
        return _today()
    return iso[:10]


def _title_from_text(text: str) -> str:
    line = text.strip().split("\n")[0]
    if len(line) > 40:
        return line[:40] + "…"
    return line or "新对话"


class ConversationStore:
    """按创建日期分片存储会话，避免单文件过大。"""

    def __init__(self, path: str | Path):
        raw = Path(path)
        if raw.suffix == ".json":
            self.dir = raw.parent / "conversations"
            legacy = raw
        else:
            self.dir = raw
            legacy = self.dir.parent / "conversations.json"
        self.dir.mkdir(parents=True, exist_ok=True)
        if legacy.exists() and not self._index_path.exists():
            self._migrate_legacy(legacy)
        if not self._index_path.exists():
            self._write_index({})

    @property
    def _index_path(self) -> Path:
        return self.dir / "index.json"

    def _shard_path(self, date: str) -> Path:
        return self.dir / f"{date}.json"

    def _read_index(self) -> dict[str, str]:
        return json.loads(self._index_path.read_text(encoding="utf-8"))

    def _write_index(self, data: dict[str, str]) -> None:
        self._index_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _read_shard(self, date: str) -> dict:
        path = self._shard_path(date)
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_shard(self, date: str, data: dict) -> None:
        self._shard_path(date).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _migrate_legacy(self, legacy_path: Path) -> None:
        data = json.loads(legacy_path.read_text(encoding="utf-8"))
        index: dict[str, str] = {}
        shards: dict[str, dict] = {}
        for cid, conv in data.items():
            date = _date_from_iso(conv.get("created_at", ""))
            index[cid] = date
            shards.setdefault(date, {})[cid] = conv
        for date, shard in shards.items():
            self._write_shard(date, shard)
        self._write_index(index)
        legacy_path.rename(legacy_path.with_suffix(".json.bak"))

    def _locate(self, cid: str) -> tuple[str, dict] | None:
        index = self._read_index()
        date = index.get(cid)
        if not date:
            return None
        shard = self._read_shard(date)
        conv = shard.get(cid)
        if conv is None:
            return None
        return date, conv

    def _save(self, cid: str, conv: dict) -> None:
        index = self._read_index()
        date = index.get(cid)
        if not date:
            date = _date_from_iso(conv.get("created_at", ""))
            index[cid] = date
            self._write_index(index)
        shard = self._read_shard(date)
        shard[cid] = conv
        self._write_shard(date, shard)

    def create(self, title: str | None = None) -> str:
        cid = uuid.uuid4().hex[:12]
        stamp = _now()
        date = _today()
        conv = {
            "id": cid,
            "title": title or "新对话",
            "created_at": stamp,
            "updated_at": stamp,
            "messages": [],
            "summarized": False,
            "summary_path": None,
            "summarized_at": None,
            "indexed_dirty": False,
        }
        index = self._read_index()
        index[cid] = date
        self._write_index(index)
        shard = self._read_shard(date)
        shard[cid] = conv
        self._write_shard(date, shard)
        return cid

    def get(self, cid: str) -> dict:
        located = self._locate(cid)
        if located is None:
            raise KeyError(cid)
        return located[1]

    def list_all(self) -> list[dict]:
        index = self._read_index()
        shards_cache: dict[str, dict] = {}
        items: list[dict] = []
        for cid, date in index.items():
            if date not in shards_cache:
                shards_cache[date] = self._read_shard(date)
            conv = shards_cache[date].get(cid)
            if conv is None:
                continue
            items.append(
                {
                    "id": conv["id"],
                    "title": conv["title"],
                    "created_at": conv["created_at"],
                    "updated_at": conv["updated_at"],
                    "message_count": len(conv.get("messages", [])),
                    "summarized": bool(conv.get("summarized")),
                    "summary_path": conv.get("summary_path"),
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
        located = self._locate(cid)
        if located is None:
            raise KeyError(cid)
        _, conv = located

        user_msg = {"role": "user", "text": user_text, "ts": user_ts or _now()}
        conv["messages"].append(user_msg)
        conv["messages"].append(assistant_msg)
        conv["updated_at"] = _now()
        if conv["title"] == "新对话" and user_text.strip():
            conv["title"] = _title_from_text(user_text)
        conv["indexed_dirty"] = True
        if conv.get("summarized"):
            conv["summarized"] = False
        self._save(cid, conv)
        return conv

    def append_messages(self, cid: str, messages: list[dict]) -> dict:
        located = self._locate(cid)
        if located is None:
            raise KeyError(cid)
        _, conv = located

        conv["messages"].extend(messages)
        conv["updated_at"] = _now()
        self._save(cid, conv)
        return conv

    def delete(self, cid: str) -> None:
        located = self._locate(cid)
        if located is None:
            raise KeyError(cid)
        date, _ = located
        index = self._read_index()
        del index[cid]
        self._write_index(index)
        shard = self._read_shard(date)
        del shard[cid]
        self._write_shard(date, shard)

    def mark_question_resolved(
        self, cid: str, question_id: str, choice_label: str
    ) -> None:
        """把某条 ask_user 征询块标记为已选择，持久化用户的选择（便于重载后展示）。"""
        located = self._locate(cid)
        if located is None:
            return
        _, conv = located
        changed = False

        def patch(blocks: list) -> None:
            nonlocal changed
            for block in blocks:
                if (
                    block.get("type") == "tool"
                    and block.get("tool") == "ask_user"
                    and block.get("question_id") == question_id
                ):
                    block["choice_resolved"] = choice_label
                    changed = True
                elif block.get("type") == "parallel":
                    patch(block.get("children", []))

        for msg in conv.get("messages", []):
            if msg.get("timeline"):
                patch(msg["timeline"])
        if changed:
            conv["updated_at"] = _now()
            self._save(cid, conv)

    def mark_summarized(self, cid: str, summary_path: str) -> None:
        located = self._locate(cid)
        if located is None:
            raise KeyError(cid)
        _, conv = located
        conv["summarized"] = True
        conv["summary_path"] = summary_path
        conv["summarized_at"] = _now()
        conv["indexed_dirty"] = False
        conv["updated_at"] = _now()
        self._save(cid, conv)

    def clear_dirty(self, cid: str) -> None:
        located = self._locate(cid)
        if located is None:
            return
        _, conv = located
        if conv.get("indexed_dirty"):
            conv["indexed_dirty"] = False
            self._save(cid, conv)

    @classmethod
    def full_transcript(cls, conv: dict, *, max_chars: int = 60000) -> str:
        """整段会话稿：用于归档总结（通读全文，不做轮次截断，仅总长兜底）。"""
        lines: list[str] = []
        for msg in conv.get("messages", []):
            role = msg.get("role")
            if role == "user":
                text = (msg.get("text") or "").strip()
                if text:
                    lines.append(f"【用户】{text}")
            elif role == "assistant":
                text = cls._assistant_content(msg)
                if text:
                    lines.append(f"【助手】{text}")
                for src in cls._iter_kb_web_sources(msg):
                    lines.append(src)
        text = "\n\n".join(lines)
        if len(text) > max_chars:
            text = text[-max_chars:]
        return text

    @classmethod
    def conversation_text(cls, conv: dict, *, max_chars: int = 20000) -> str:
        """会话可检索正文（喂给全文索引）：仅用户与助手文字，去掉工具噪声。"""
        lines: list[str] = []
        for msg in conv.get("messages", []):
            role = msg.get("role")
            if role == "user":
                text = (msg.get("text") or "").strip()
                if text:
                    lines.append(text)
            elif role == "assistant":
                text = cls._assistant_content(msg)
                if text:
                    lines.append(text)
        text = "\n\n".join(lines)
        return text[:max_chars] if len(text) > max_chars else text

    @staticmethod
    def _iter_kb_web_sources(msg: dict) -> list[str]:
        out: list[str] = []
        for src in msg.get("sources") or []:
            st = src.get("type")
            if st == "web" or st == "search":
                title = src.get("title") or src.get("url") or ""
                snippet = (src.get("snippet") or "").strip()
                if title:
                    out.append(f"（来源：{title}）{snippet}".strip())
            elif st == "kb":
                path = src.get("path")
                if path:
                    out.append(f"（本地：{path}）")
        return out

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
