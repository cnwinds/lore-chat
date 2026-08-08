"""统一 SlotResolver：observe / manage / 手改新行共用。"""

from __future__ import annotations

from dataclasses import dataclass

from app.engine.memory.normalize import resolve_slot_key, value_hash
from app.engine.memory.policy import (
    allows_automatic_save,
    has_change_signal,
    infer_sensitivity,
    origin_wins_conflict,
    should_promote,
)
from app.engine.memory.store import MemoryStore
from app.engine.secrets import scan_secrets
from app.engine.memory.constants import ORIGIN_RANK


@dataclass
class SlotAction:
    slot_key: str
    action: str  # merge | replace | noop | new
    statement: str
    category: str
    origin: str
    confidence: float = 0.9


class SlotResolver:
    def __init__(self, store: MemoryStore):
        self.store = store

    def apply(
        self,
        action: SlotAction,
        *,
        conversation_id: str | None = None,
    ) -> dict:
        statement = (action.statement or "").strip()
        if not statement:
            return {"ok": False, "error": "empty_statement", "message": "记忆内容不能为空"}
        if scan_secrets(statement):
            return {
                "ok": False,
                "error": "secret_rejected",
                "message": "检测到密钥或敏感凭据，不能写入长期记忆",
            }

        existing = _align_view(self.store)
        slot = resolve_slot_key(
            action.category,
            statement,
            slot_hint=action.slot_key,
            existing=existing,
        )
        category = (action.category or "preference").strip().lower()
        origin = (action.origin or "direct").strip()
        act = (action.action or "new").strip().lower()
        if act not in ("merge", "replace", "noop", "new"):
            act = "new"

        sensitivity = infer_sensitivity(statement)
        if not allows_automatic_save(sensitivity, origin):
            return {"ok": False, "error": "rejected", "message": "敏感内容未获授权，已拒绝"}

        vhash = value_hash(statement)
        if self.store.has_tombstone(slot_key=slot, normalized_value_hash=vhash):
            return {
                "ok": False,
                "error": "tombstoned",
                "message": "该记忆已被用户遗忘，需显式重新记住",
            }
        if self.store.has_tombstone(slot_key=slot, normalized_value_hash=None):
            return {
                "ok": False,
                "error": "tombstoned",
                "message": "该记忆槽位已被阻止",
            }

        status = _initial_status(origin, statement)
        existing_same = self.store.find_by_slot_and_hash(slot, vhash)
        confirmed_in_slot = self.store.find_confirmed_by_slot(slot)
        active_primary = _pick_primary(confirmed_in_slot, self.store.list_candidates(), slot)

        if act == "noop" and active_primary:
            if conversation_id:
                self.store.add_session_evidence(active_primary["id"], conversation_id)
                self._maybe_promote(active_primary["id"])
            else:
                self.store.set_last_seen_at(active_primary["id"])
            return {
                "ok": True,
                "fact": self.store.get_fact(active_primary["id"]),
                "action": "noop",
            }

        # 同槽已有 confirmed 或 candidate：new 改为 merge/replace，避免平行开槽
        if act == "new" and active_primary:
            act = "replace" if has_change_signal(statement) else "merge"

        # 同槽就地更新，保留 fact id 与既有会话出处
        if act in ("merge", "replace") and active_primary:
            if not _may_overwrite(origin, active_primary.get("origin", "inferred")):
                if conversation_id:
                    self.store.add_session_evidence(active_primary["id"], conversation_id)
                return {
                    "ok": True,
                    "fact": active_primary,
                    "action": "noop",
                    "message": "低优先级来源未覆盖现有记忆",
                }
            self.store.supersede_others_in_slot(slot, keep_id=active_primary["id"])
            merged_origin = active_primary["origin"]
            if ORIGIN_RANK.get(origin, 0) > ORIGIN_RANK.get(merged_origin, 0):
                merged_origin = origin
            fact = self.store.update_fact_content(
                active_primary["id"],
                statement=statement,
                normalized_value_hash=vhash,
                category=category,
                origin=merged_origin,
                confidence=max(float(active_primary.get("confidence") or 0), float(action.confidence)),
                sensitivity=sensitivity,
                status="confirmed" if status == "confirmed" else active_primary.get("status"),
            )
            if conversation_id:
                self.store.add_session_evidence(fact["id"], conversation_id)
                fact = self._maybe_promote(fact["id"]) or fact
            return {"ok": True, "fact": fact, "action": act}

        if existing_same and existing_same["status"] in ("forgotten", "superseded", "rejected"):
            if origin not in ("manual", "explicit_remember"):
                return {"ok": False, "error": "inactive", "message": "事实已失效"}

        # 无主 fact：新建；若同槽有其他 confirmed/candidate 则先 supersede
        if status == "confirmed":
            self.store.supersede_others_in_slot(slot, keep_id=None)

        fact = self.store.upsert_fact(
            slot_key=slot,
            category=category,
            statement=statement,
            normalized_value_hash=vhash,
            origin=origin,
            confidence=float(action.confidence),
            sensitivity=sensitivity,
            status=status,
        )
        if conversation_id:
            self.store.add_session_evidence(fact["id"], conversation_id)
            fact = self._maybe_promote(fact["id"]) or fact
        return {"ok": True, "fact": fact, "action": act if act != "noop" else "new"}

    def apply_statement(
        self,
        statement: str,
        *,
        origin: str = "explicit_remember",
        category: str | None = None,
        slot_key: str | None = None,
        conversation_id: str | None = None,
        action: str = "merge",
        confidence: float = 1.0,
        clear_tombstone: bool = False,
    ) -> dict:
        from app.engine.memory.normalize import infer_category

        cat = category or infer_category(statement)
        existing = _align_view(self.store)
        slot = resolve_slot_key(
            cat, statement, slot_hint=slot_key, existing=existing
        )
        vhash = value_hash(statement)
        if clear_tombstone:
            self.store.clear_tombstone(slot_key=slot, normalized_value_hash=vhash)
        return self.apply(
            SlotAction(
                slot_key=slot,
                action=action,
                statement=statement,
                category=cat,
                origin=origin,
                confidence=confidence,
            ),
            conversation_id=conversation_id,
        )

    def _maybe_promote(self, fact_id: str) -> dict | None:
        fact = self.store.get_fact(fact_id)
        if not fact:
            return None
        distinct = self.store.count_distinct_conversation_evidence(fact_id)
        if should_promote(
            fact,
            distinct_conversations=distinct,
            evidence_count=distinct,
        ):
            return self.store.update_fact_content(
                fact_id,
                statement=fact["statement"],
                normalized_value_hash=fact["normalized_value_hash"],
                status="confirmed",
            )
        return fact


def _align_view(store: MemoryStore) -> list[dict]:
    """confirmed + candidate，供近义对齐（晋升前也要并到同槽）。"""
    rows: list[dict] = []
    for f in store.list_confirmed():
        rows.append(
            {
                "slot_key": f["slot_key"],
                "statement": f["statement"],
                "category": f.get("category"),
            }
        )
    for f in store.list_candidates():
        rows.append(
            {
                "slot_key": f["slot_key"],
                "statement": f["statement"],
                "category": f.get("category"),
            }
        )
    return rows


def _initial_status(origin: str, statement: str) -> str:
    if origin in ("manual", "explicit_remember"):
        return "confirmed"
    if origin == "direct":
        return "confirmed"
    return "candidate"


def _pick_primary(
    confirmed: list[dict], candidates: list[dict], slot: str
) -> dict | None:
    if confirmed:
        return sorted(confirmed, key=lambda f: f.get("updated_at") or "", reverse=True)[0]
    slot_cands = [c for c in candidates if c["slot_key"] == slot]
    if slot_cands:
        return sorted(slot_cands, key=lambda f: f.get("updated_at") or "", reverse=True)[0]
    return None


def _may_overwrite(new_origin: str, old_origin: str) -> bool:
    if origin_wins_conflict(new_origin, old_origin):
        return True
    if new_origin == old_origin:
        return True
    # direct 可更新同级；inferred 不可覆盖 direct/manual
    return ORIGIN_RANK.get(new_origin, 0) >= ORIGIN_RANK.get(old_origin, 0)
