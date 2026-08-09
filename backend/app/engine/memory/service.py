from __future__ import annotations

import hashlib
from dataclasses import dataclass

from app.engine.memory.constants import MEMORY_DOC_REL
from app.engine.memory.renderer import MemoryRenderer
from app.engine.memory.resolver import SlotResolver
from app.engine.memory.store import MemoryStore
from app.engine.secrets import scan_secrets
from app.engine.knowledge_writer import KnowledgeWriter
from app.storage.repo import KnowledgeRepo


@dataclass
class MemoryActionResult:
    ok: bool
    error: str | None = None
    fact: dict | None = None
    message: str = ""


class MemoryService:
    def __init__(
        self,
        store: MemoryStore,
        repo: KnowledgeRepo,
        *,
        memory_rel: str = MEMORY_DOC_REL,
        memory_max_chars: int = 4000,
        conversations=None,
        knowledge_writer: KnowledgeWriter,
    ):
        self.store = store
        self.repo = repo
        self.memory_rel = memory_rel
        self.memory_max_chars = memory_max_chars
        self.conversations = conversations
        self.knowledge_writer = knowledge_writer
        self.resolver = SlotResolver(store)
        self._purge_legacy_projection_file()
        # 迁移/换槽后出处曾留在 superseded 上，导致面板跳转全禁用
        try:
            self.store.repair_evidence_following_supersede()
        except Exception as exc:  # noqa: BLE001
            from app.logging_config import get_logger

            get_logger("memory").warning(
                "repair_evidence_following_supersede failed: %s",
                exc,
                exc_info=True,
            )

    def _drop_memory_from_search_index(self) -> None:
        self.knowledge_writer.drop_from_index([self.memory_rel])

    def _purge_legacy_projection_file(self) -> None:
        """一次性移除旧版「系统/记忆.md」投影（git commit），避免与 DB 双写漂移。"""
        try:
            removed = self.repo.remove_file(
                self.memory_rel,
                commit_msg="memory: remove legacy projection file",
                allow_protected=True,
            )
        except ValueError:
            return
        if removed:
            self._drop_memory_from_search_index()

    def render_context(self) -> str:
        """从 DB 渲染容量裁剪后的注入文本（不落盘）。"""
        facts = self.store.list_confirmed()
        if not facts:
            return ""
        renderer = MemoryRenderer(max_chars=self.memory_max_chars)
        body = renderer.render(facts)
        return MemoryRenderer.strip_for_injection(body)

    def remember(
        self,
        statement: str,
        *,
        origin: str = "explicit_remember",
        conversation_id: str | None = None,
        message_id: str | None = None,
        start_char: int | None = None,
        end_char: int | None = None,
        clear_tombstone: bool = False,
    ) -> dict:
        text = (statement or "").strip()
        if not text:
            return {"ok": False, "error": "empty_statement", "message": "记忆内容不能为空"}
        if scan_secrets(text):
            return {
                "ok": False,
                "error": "secret_rejected",
                "message": "检测到密钥或敏感凭据，不能写入长期记忆",
            }
        out = self.resolver.apply_statement(
            text,
            origin=origin,
            conversation_id=conversation_id,
            action="merge",
            confidence=1.0,
            clear_tombstone=clear_tombstone,
        )
        if not out.get("ok"):
            return out
        fact = out.get("fact") or {}
        # 兼容旧调用方：若仍传入字级区间则额外记一条（会话级出处已由 Resolver 写入）
        if (
            fact.get("id")
            and conversation_id
            and message_id
            and start_char is not None
            and end_char is not None
        ):
            msg_text = text
            if self.conversations:
                msg = self.conversations.get_message(message_id)
                if msg:
                    msg_text = msg.get("text") or text
            quote = msg_text[start_char:end_char]
            self.store.add_evidence(
                fact_id=fact["id"],
                conversation_id=conversation_id,
                message_id=message_id,
                start_char=start_char,
                end_char=end_char,
                quote_hash=hashlib.sha256(quote.encode("utf-8")).hexdigest(),
            )
        return {"ok": True, "fact": fact, "message": "已记住"}

    def forget(self, *, fact_id: str | None = None, statement: str = "") -> dict:
        return self.resolver.forget(fact_id=fact_id, statement=statement)

    def list_panel_facts(self) -> dict:
        """Phase 2：面板列表（confirmed + candidate + 会话出处）。"""
        items = []
        for f in self.store.list_confirmed() + self.store.list_candidates():
            cids = sorted(
                {
                    ev["conversation_id"]
                    for ev in self.store.list_evidence(f["id"])
                    if ev.get("conversation_id")
                }
            )
            items.append(
                {
                    "id": f["id"],
                    "slot_key": f["slot_key"],
                    "statement": f["statement"],
                    "category": f.get("category"),
                    "origin": f.get("origin"),
                    "status": f.get("status"),
                    "confidence": f.get("confidence"),
                    "conversation_ids": cids,
                    "updated_at": f.get("updated_at"),
                }
            )
        # 待确认置顶（审阅优先）；组内按更新时间倒序
        def updated_at(row: dict) -> str:
            return row.get("updated_at") or ""

        candidates = [x for x in items if x.get("status") == "candidate"]
        others = [x for x in items if x.get("status") != "candidate"]
        candidates.sort(key=updated_at, reverse=True)
        others.sort(key=updated_at, reverse=True)
        return {"facts": candidates + others, "count": len(items)}

    def confirm_candidate(self, fact_id: str) -> dict:
        return self.resolver.confirm_candidate(fact_id)

    def reject_candidate(self, fact_id: str) -> dict:
        return self.resolver.reject_candidate(fact_id)

    def edit_fact(self, fact_id: str, statement: str) -> dict:
        return self.resolver.edit_fact(fact_id, statement)

    def correct(
        self,
        *,
        fact_id: str | None = None,
        statement: str = "",
        replacement: str,
    ) -> dict:
        return self.resolver.correct(
            fact_id=fact_id, statement=statement, replacement=replacement
        )

    def recall(self, query: str, *, include_sources: bool = False, limit: int = 10) -> dict:
        facts = self.store.search_confirmed(query, limit=limit)
        out_facts = []
        for f in facts:
            item = {
                "fact_id": f["id"],
                "statement": f["statement"],
                "category": f["category"],
                "origin": f["origin"],
            }
            if include_sources:
                item["sources"] = self._explain_sources(f["id"], sensitivity=f.get("sensitivity", "normal"))
            out_facts.append(item)
        return {"facts": out_facts, "count": len(out_facts)}

    def _explain_sources(self, fact_id: str, *, sensitivity: str = "normal") -> list[dict]:
        sources: list[dict] = []
        for ev in self.store.list_evidence(fact_id):
            quote = None
            available = False
            if sensitivity != "sensitive" and self.conversations:
                msg = self.conversations.get_message(ev["message_id"])
                if msg:
                    text = msg.get("text") or ""
                    quote = text[ev["start_char"] : ev["end_char"]]
                    qh = hashlib.sha256(quote.encode("utf-8")).hexdigest()
                    available = qh == ev["quote_hash"]
            sources.append(
                {
                    "conversation_id": ev["conversation_id"],
                    "message_id": ev["message_id"],
                    "start_char": ev["start_char"],
                    "end_char": ev["end_char"],
                    "quote": quote if available else None,
                    "source_available": available,
                    "offset_version": "unicode-codepoint-v1",
                }
            )
        return sources
