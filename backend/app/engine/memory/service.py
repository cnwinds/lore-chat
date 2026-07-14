from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from app.engine.memory.constants import MEMORY_DOC_REL
from app.engine.memory.normalize import infer_category, normalize_slot_key, value_hash
from app.engine.memory.policy import infer_sensitivity
from app.engine.memory.store import MemoryStore
from app.engine.secrets import scan_secrets
from app.storage.repo import KnowledgeRepo

_MARKER_RE = re.compile(r"<!--\s*memory:([A-Za-z0-9_-]+)\s*-->")


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
        indexer=None,
    ):
        self.store = store
        self.repo = repo
        self.memory_rel = memory_rel
        self.memory_max_chars = memory_max_chars
        self.conversations = conversations
        self.indexer = indexer

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
        category = infer_category(text)
        slot = normalize_slot_key(category, text)
        vhash = value_hash(text)
        if self.store.has_tombstone(slot_key=slot, normalized_value_hash=vhash):
            if clear_tombstone:
                self.store.clear_tombstone(slot_key=slot, normalized_value_hash=vhash)
            else:
                return {
                    "ok": False,
                    "error": "tombstoned",
                    "message": "该记忆已被用户遗忘，需显式重新记住",
                }
        sensitivity = infer_sensitivity(text)
        fact = self.store.upsert_fact(
            slot_key=slot,
            category=category,
            statement=text,
            normalized_value_hash=vhash,
            origin=origin,
            confidence=1.0,
            sensitivity=sensitivity,
        )
        if conversation_id and message_id and start_char is not None and end_char is not None:
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
        fact = None
        if fact_id:
            fact = self.store.get_fact(fact_id)
        elif statement.strip():
            hits = self.store.search_confirmed(statement.strip(), limit=2)
            if len(hits) == 1:
                fact = hits[0]
            elif len(hits) > 1:
                return {
                    "ok": False,
                    "error": "ambiguous",
                    "candidates": [{"fact_id": h["id"], "statement": h["statement"]} for h in hits],
                    "message": "匹配到多条记忆，请指定 fact_id",
                }
        if not fact:
            return {"ok": False, "error": "not_found", "message": "未找到要遗忘的记忆"}
        self.store.mark_forgotten(fact["id"], reason="user_forget")
        return {"ok": True, "fact_id": fact["id"], "message": "已遗忘"}

    def correct(
        self,
        *,
        fact_id: str | None = None,
        statement: str = "",
        replacement: str,
    ) -> dict:
        rep = (replacement or "").strip()
        if not rep:
            return {"ok": False, "error": "empty_replacement", "message": "更正内容不能为空"}
        if scan_secrets(rep):
            return {"ok": False, "error": "secret_rejected", "message": "更正内容含密钥，已拒绝"}
        fact = self.store.get_fact(fact_id) if fact_id else None
        if not fact and statement.strip():
            hits = self.store.search_confirmed(statement.strip(), limit=2)
            if len(hits) == 1:
                fact = hits[0]
        if not fact:
            return {"ok": False, "error": "not_found", "message": "未找到要更正的记忆"}
        self.store.mark_forgotten(fact["id"], reason="superseded")
        out = self.remember(rep, origin="manual")
        if out.get("ok") and out.get("fact"):
            return {"ok": True, "fact": out["fact"], "message": "已更正记忆"}
        return out

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

    def render_to_file(self) -> str:
        from app.engine.memory.renderer import MemoryRenderer

        renderer = MemoryRenderer(self.repo, memory_rel=self.memory_rel, max_chars=self.memory_max_chars)
        facts = self.store.list_confirmed()
        state = self.store.get_render_state()
        revision = int(state.get("revision") or 0) + 1
        body = renderer.render(facts, revision=revision)
        meta = {
            "title": "记忆 · 关于用户",
            "source": "system",
            "schema_version": 1,
            "memory_revision": revision,
        }
        try:
            self.repo.write_doc(self.memory_rel, meta, body, commit_msg="memory: render projection")
        except FileNotFoundError:
            self.repo.write_doc(self.memory_rel, meta, body, commit_msg="memory: seed projection")
        rendered_ids = [f["id"] for f in facts if f["id"] in _extract_rendered_ids(body)]
        abs_p = self.repo.abs_path(self.memory_rel)
        fh = hashlib.sha256(body.encode("utf-8")).hexdigest()
        self.store.save_render_state(
            revision=revision,
            file_hash=fh,
            file_mtime=abs_p.stat().st_mtime,
            rendered_fact_ids=rendered_ids,
            valid_snapshot_body=body,
        )
        if self.indexer:
            try:
                self.indexer.remove_doc(self.memory_rel)
            except Exception:
                pass
        return body

    def import_manual_document(self, meta: dict, body: str, *, dry_run: bool = False) -> dict:
        from app.engine.memory.renderer import MemoryRenderer

        renderer = MemoryRenderer(self.repo, memory_rel=self.memory_rel, max_chars=self.memory_max_chars)
        parsed = renderer.parse(body)
        if not parsed["valid"]:
            return {"ok": False, "error": "invalid_structure", "message": parsed.get("error", "结构校验失败")}
        tombstone_err = self._check_import_tombstones(parsed["items"])
        if tombstone_err:
            return tombstone_err
        if dry_run:
            return {"ok": True, "message": "校验通过"}
        state = self.store.get_render_state()
        prev_ids = set(renderer.loads_rendered_ids(state.get("rendered_fact_ids_json") or "[]"))
        current_ids = {item["fact_id"] for item in parsed["items"] if item.get("fact_id")}
        for fid in prev_ids - current_ids:
            fact = self.store.get_fact(fid)
            if fact and fact["status"] == "confirmed":
                self.store.mark_forgotten(fid, reason="manual_delete")
        for item in parsed["items"]:
            stmt = item["statement"]
            cat = item["category"]
            slot = normalize_slot_key(cat, stmt)
            vhash = value_hash(stmt)
            if scan_secrets(stmt):
                return {"ok": False, "error": "secret_rejected", "message": "手动编辑含密钥，已拒绝"}
            sensitivity = infer_sensitivity(stmt)
            if item.get("fact_id"):
                self.store.upsert_fact(
                    slot_key=slot,
                    category=cat,
                    statement=stmt,
                    normalized_value_hash=vhash,
                    origin="manual",
                    fact_id=item["fact_id"],
                    sensitivity=sensitivity,
                )
            else:
                self.remember(stmt, origin="manual")
        revision = int(meta.get("memory_revision") or state.get("revision") or 0)
        abs_p = self.repo.abs_path(self.memory_rel)
        fh = hashlib.sha256(body.encode("utf-8")).hexdigest()
        self.store.save_render_state(
            revision=revision,
            file_hash=fh,
            file_mtime=abs_p.stat().st_mtime if abs_p.exists() else None,
            rendered_fact_ids=list(current_ids),
            valid_snapshot_body=body,
        )
        if self.indexer:
            try:
                self.indexer.remove_doc(self.memory_rel)
            except Exception:
                pass
        return {"ok": True, "message": "手动编辑已同步"}

    def _check_import_tombstones(self, items: list[dict]) -> dict | None:
        for item in items:
            stmt = item["statement"]
            cat = infer_category(stmt)
            slot = normalize_slot_key(cat, stmt)
            vhash = value_hash(stmt)
            if self.store.has_tombstone(slot_key=slot, normalized_value_hash=vhash):
                return {
                    "ok": False,
                    "error": "tombstoned",
                    "message": "该记忆已被遗忘，无法通过编辑复活",
                }
        return None


def _extract_rendered_ids(body: str) -> set[str]:
    return set(_MARKER_RE.findall(body))
