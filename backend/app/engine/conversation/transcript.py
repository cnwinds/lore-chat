"""会话只读文本投影：归档稿 / LLM history / 索引正文 / context excerpt。"""

from __future__ import annotations

from collections.abc import Iterable


class ConversationTranscript:
    """从 conv dict 投影文本视图（不碰 SQLite）。"""

    @classmethod
    def _message_transcript_line(cls, msg: dict) -> str:
        role = msg.get("role")
        if role == "user":
            text = (msg.get("text") or "").strip()
            return f"【用户】{text}" if text else ""
        if role == "assistant":
            parts: list[str] = []
            text = cls.assistant_content(msg)
            if text:
                parts.append(f"【助手】{text}")
            parts.extend(cls.iter_kb_web_sources(msg))
            return "\n".join(parts)
        return ""

    @classmethod
    def iter_segments(cls, conv: dict, *, max_chars: int) -> Iterable[dict]:
        batch: list[dict] = []
        used = 0
        for msg in conv.get("messages", []):
            if msg.get("role") not in ("user", "assistant"):
                continue
            piece = cls._message_transcript_line(msg)
            if not piece:
                continue
            plen = len(piece)
            if batch and used + plen > max_chars:
                yield {
                    "messages": batch,
                    "first_message_id": batch[0]["id"],
                    "last_message_id": batch[-1]["id"],
                    "text": "\n\n".join(cls._message_transcript_line(m) for m in batch),
                }
                batch, used = [], 0
            batch.append(msg)
            used += plen + 2
        if batch:
            yield {
                "messages": batch,
                "first_message_id": batch[0]["id"],
                "last_message_id": batch[-1]["id"],
                "text": "\n\n".join(cls._message_transcript_line(m) for m in batch),
            }

    @classmethod
    def full(cls, conv: dict, *, max_chars: int = 60000) -> str:
        """整段会话稿：用于归档总结（通读全文，不做轮次截断，仅总长兜底）。"""
        lines: list[str] = []
        for msg in conv.get("messages", []):
            role = msg.get("role")
            if role == "user":
                text = (msg.get("text") or "").strip()
                if text:
                    lines.append(f"【用户】{text}")
            elif role == "assistant":
                text = cls.assistant_content(msg)
                if text:
                    lines.append(f"【助手】{text}")
                for src in cls.iter_kb_web_sources(msg):
                    lines.append(src)
        text = "\n\n".join(lines)
        if len(text) > max_chars:
            text = text[-max_chars:]
        return text

    @classmethod
    def indexable_text(cls, conv: dict, *, max_chars: int = 20000) -> str:
        """会话可检索正文（喂给全文索引）：仅用户与助手文字，去掉工具噪声。"""
        lines: list[str] = []
        for msg in conv.get("messages", []):
            role = msg.get("role")
            if role == "user":
                text = (msg.get("text") or "").strip()
                if text:
                    lines.append(text)
            elif role == "assistant":
                text = cls.assistant_content(msg)
                if text:
                    lines.append(text)
        text = "\n\n".join(lines)
        return text[:max_chars] if len(text) > max_chars else text

    @staticmethod
    def iter_kb_web_sources(msg: dict) -> list[str]:
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
    def assistant_content(msg: dict) -> str:
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
                text = cls.assistant_content(msg)
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

    @classmethod
    def context_excerpt(cls, conv: dict, *, max_chars: int = 4000) -> str:
        lines: list[str] = []
        for msg in conv.get("messages", [])[-8:]:
            role = msg.get("role")
            if role == "user" and msg.get("text"):
                lines.append(f"用户：{msg['text']}")
            elif role == "assistant":
                text = cls.assistant_content(msg)
                if text:
                    lines.append(f"助手：{text[:800]}")
                elif msg.get("timeline"):
                    for block in msg["timeline"]:
                        if block.get("type") == "tool" and block.get("tool") in (
                            "ask_user",
                            "sandbox_run",
                        ):
                            q = block.get("question") or block.get("summary") or ""
                            if q:
                                lines.append(f"助手征询：{q}")
        text = "\n".join(lines)
        return text[:max_chars] if len(text) > max_chars else text


__all__ = ["ConversationTranscript"]
