"""统一 SlotResolver：observe / manage / 手改新行共用。"""

from __future__ import annotations

from dataclasses import dataclass

from app.engine.memory.normalize import (
    is_abstract_slot_key,
    resolve_slot_key,
    value_hash,
)
from app.engine.memory.policy import (
    allows_automatic_save,
    has_change_signal,
    infer_sensitivity,
    initial_status,
    origin_wins_conflict,
    should_promote,
)
from app.engine.memory.store import MemoryStore
from app.engine.secrets import scan_secrets
from app.engine.memory.constants import ORIGIN_RANK


@dataclass(init=False)
class SlotAction:
    """抽取/调用方只填 slot_hint；canonical slot_key 由 SlotResolver.apply 解析。"""

    action: str  # merge | replace | noop | new
    statement: str
    category: str
    origin: str
    confidence: float
    slot_hint: str

    def __init__(
        self,
        *,
        action: str,
        statement: str,
        category: str,
        origin: str,
        confidence: float = 0.9,
        slot_hint: str = "",
        slot_key: str = "",
    ) -> None:
        self.action = action
        self.statement = statement
        self.category = category
        self.origin = origin
        self.confidence = confidence
        # slot_key= 为旧调用方别名，语义同 slot_hint（未解析）
        self.slot_hint = slot_hint or slot_key

    @property
    def slot_key(self) -> str:
        """未解析 hint 的兼容别名；勿当成库内最终槽位。"""
        return self.slot_hint


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
            slot_hint=action.slot_hint,
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
        # 同值最多一条存活：并入已有条；目标槽位阶更高时可升格迁槽（migrate）
        active_same = self.store.find_active_by_value_hash(vhash)
        slot_promoted = False
        if active_same:
            live = active_same.get("slot_key") or ""
            if live != slot:
                if _slot_rank(slot, vhash) > _slot_rank(live, vhash):
                    active_same = (
                        self.store.reassign_slot_key(active_same["id"], slot)
                        or active_same
                    )
                    slot = active_same.get("slot_key") or slot
                    slot_promoted = True
                else:
                    slot = live
        else:
            if self.store.has_value_tombstone(vhash) or self.store.has_tombstone(
                slot_key=slot, normalized_value_hash=vhash
            ):
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

        status = initial_status(origin, statement)
        existing_same = self.store.find_by_slot_and_hash(slot, vhash)
        confirmed_in_slot = self.store.find_confirmed_by_slot(slot)
        stale_in_slot = self.store.find_stale_by_slot(slot)
        active_primary = _pick_primary(
            confirmed_in_slot,
            self.store.list_candidates(),
            slot,
            stale=stale_in_slot,
        )

        if act == "noop" and active_primary:
            fact = _apply_noop_touch(
                self.store,
                active_primary,
                incoming_origin=origin,
                incoming_confidence=float(action.confidence),
            )
            # 升格迁槽后 noop 不走 merge，须单独写回 category
            if slot_promoted and category != (fact.get("category") or ""):
                fact = (
                    self.store.update_fact_content(
                        fact["id"],
                        statement=fact["statement"],
                        normalized_value_hash=fact["normalized_value_hash"],
                        category=category,
                        status=fact.get("status"),
                    )
                    or fact
                )
            if conversation_id:
                self.store.add_session_evidence(fact["id"], conversation_id)
                fact = self._maybe_promote(fact["id"]) or self.store.get_fact(fact["id"]) or fact
            else:
                self.store.set_last_seen_at(fact["id"])
                fact = self.store.get_fact(fact["id"]) or fact
            return {"ok": True, "fact": fact, "action": "noop"}

        # 同槽已有 confirmed / candidate / stale：new 改为 merge/replace，避免平行开槽
        if act == "new" and active_primary:
            act = "replace" if has_change_signal(statement) else "merge"

        # 同槽就地更新，保留 fact id 与既有会话出处
        if act in ("merge", "replace") and active_primary:
            if not _may_overwrite(origin, active_primary.get("origin", "inferred")):
                fact = active_primary
                if conversation_id:
                    self.store.add_session_evidence(active_primary["id"], conversation_id)
                if active_primary.get("status") == "stale":
                    # 不能改写内容时仍应复活，避免衰减后永久不可见
                    revive = initial_status(
                        active_primary.get("origin") or "inferred",
                        active_primary.get("statement") or statement,
                    )
                    fact = self.store.update_fact_content(
                        active_primary["id"],
                        statement=active_primary["statement"],
                        normalized_value_hash=active_primary["normalized_value_hash"],
                        status=revive,
                    ) or active_primary
                return {
                    "ok": True,
                    "fact": fact,
                    "action": "noop",
                    "message": "低优先级来源未覆盖现有记忆",
                }
            self.store.supersede_others_in_slot(slot, keep_id=active_primary["id"])
            merged_origin = active_primary["origin"]
            if ORIGIN_RANK.get(origin, 0) > ORIGIN_RANK.get(merged_origin, 0):
                merged_origin = origin
            next_status = _status_after_touch(active_primary, status)
            fact = self.store.update_fact_content(
                active_primary["id"],
                statement=statement,
                normalized_value_hash=vhash,
                category=category,
                origin=merged_origin,
                confidence=max(float(active_primary.get("confidence") or 0), float(action.confidence)),
                sensitivity=sensitivity,
                status=next_status,
            )
            if conversation_id:
                self.store.add_session_evidence(fact["id"], conversation_id)
                fact = self._maybe_promote(fact["id"]) or fact
            return {"ok": True, "fact": fact, "action": act}

        if existing_same and existing_same["status"] in ("forgotten", "superseded", "rejected"):
            if origin not in ("manual", "explicit_remember"):
                return {"ok": False, "error": "inactive", "message": "事实已失效"}

        # 无主 fact：先新建，再以新 id 为 keep supersede，以便出处 rebind 到存活条
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
        if status == "confirmed":
            self.store.supersede_others_in_slot(slot, keep_id=fact["id"])
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
            self.store.clear_value_tombstones(vhash)
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

    def confirm_candidate(self, fact_id: str) -> dict:
        fact = self.store.get_fact(fact_id)
        if not fact:
            return {"ok": False, "error": "not_found", "message": "未找到记忆"}
        if fact.get("status") != "candidate":
            return {
                "ok": False,
                "error": "invalid_status",
                "message": "仅 candidate 可确认晋升",
            }
        slot = fact["slot_key"]
        self.store.supersede_others_in_slot(slot, keep_id=fact_id)
        updated = self.store.update_fact_content(
            fact_id,
            statement=fact["statement"],
            normalized_value_hash=fact["normalized_value_hash"],
            status="confirmed",
        )
        return {"ok": True, "fact": updated, "message": "已确认晋升"}

    def reject_candidate(self, fact_id: str) -> dict:
        fact = self.store.get_fact(fact_id)
        if not fact:
            return {"ok": False, "error": "not_found", "message": "未找到记忆"}
        if fact.get("status") != "candidate":
            return {
                "ok": False,
                "error": "invalid_status",
                "message": "仅 candidate 可拒绝",
            }
        self.store.set_status(fact_id, "rejected")
        return {"ok": True, "fact_id": fact_id, "message": "已拒绝"}

    def edit_fact(self, fact_id: str, statement: str) -> dict:
        text = (statement or "").strip()
        if not text:
            return {"ok": False, "error": "empty_statement", "message": "内容不能为空"}
        if scan_secrets(text):
            return {
                "ok": False,
                "error": "secret_rejected",
                "message": "检测到密钥或敏感凭据，不能写入长期记忆",
            }
        fact = self.store.get_fact(fact_id)
        if not fact or fact.get("status") not in ("confirmed", "candidate"):
            return {"ok": False, "error": "not_found", "message": "未找到可编辑记忆"}
        old_hash = fact["normalized_value_hash"]
        new_hash = value_hash(text)
        self.store.clear_tombstone(
            slot_key=fact["slot_key"], normalized_value_hash=new_hash
        )
        self.store.clear_topic_fingerprint_tombstones(
            normalized_value_hash=new_hash
        )
        updated = self.store.update_fact_content(
            fact_id,
            statement=text,
            normalized_value_hash=new_hash,
            origin="manual",
            status=fact.get("status"),
        )
        updated = self.store.get_fact(fact_id) or updated
        self.store.supersede_others_in_slot(
            updated.get("slot_key") or fact["slot_key"], keep_id=fact_id
        )
        if new_hash != old_hash:
            self.store.block_value(
                slot_key=fact["slot_key"],
                normalized_value_hash=old_hash,
                reason="superseded",
            )
        return {"ok": True, "fact": updated, "message": "已更新"}

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
        if fact.get("status") not in ("confirmed", "candidate", "stale"):
            return {"ok": False, "error": "not_found", "message": "未找到要更正的记忆"}
        old_hash = fact["normalized_value_hash"]
        new_hash = value_hash(rep)
        if new_hash == old_hash and fact.get("statement") == rep:
            return {"ok": True, "fact": fact, "message": "无需更正"}
        self.store.clear_tombstone(
            slot_key=fact["slot_key"], normalized_value_hash=new_hash
        )
        self.store.clear_topic_fingerprint_tombstones(
            normalized_value_hash=new_hash
        )
        updated = self.store.update_fact_content(
            fact["id"],
            statement=rep,
            normalized_value_hash=new_hash,
            category=fact.get("category"),
            origin="manual",
            status="confirmed",
        )
        if not updated:
            return {"ok": False, "error": "update_failed", "message": "更正失败"}
        updated = self.store.get_fact(fact["id"]) or updated
        self.store.supersede_others_in_slot(
            updated.get("slot_key") or fact["slot_key"], keep_id=fact["id"]
        )
        if new_hash != old_hash:
            self.store.block_value(
                slot_key=fact["slot_key"],
                normalized_value_hash=old_hash,
                reason="superseded",
            )
        return {
            "ok": True,
            "fact": self.store.get_fact(fact["id"]) or updated,
            "message": "已更正记忆",
        }

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
                    "candidates": [
                        {"fact_id": h["id"], "statement": h["statement"]} for h in hits
                    ],
                    "message": "匹配到多条记忆，请指定 fact_id",
                }
        if not fact:
            return {"ok": False, "error": "not_found", "message": "未找到要遗忘的记忆"}
        self.store.mark_forgotten(fact["id"], reason="user_forget")
        return {"ok": True, "fact_id": fact["id"], "message": "已遗忘"}

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


def _slot_rank(slot_key: str, vhash: str) -> int:
    """槽位阶：命名抽象/种子 > topic 指纹 > 旧 stem/open。用于同值升格。"""
    sk = slot_key or ""
    tip = f".topic_{vhash[:12]}"
    if is_abstract_slot_key(sk) and not sk.endswith(tip):
        return 2
    if sk.endswith(tip):
        return 1
    return 0


def _align_view(store: MemoryStore) -> list[dict]:
    """confirmed + candidate + stale，供近义对齐（衰减后仍并到同槽）。"""
    rows: list[dict] = []
    for f in store.list_active_facts():
        rows.append(
            {
                "slot_key": f["slot_key"],
                "statement": f["statement"],
                "category": f.get("category"),
            }
        )
    return rows


def _merge_origin(old: str | None, new: str | None) -> str:
    o = (old or "inferred").strip()
    n = (new or "inferred").strip()
    if ORIGIN_RANK.get(n, 0) > ORIGIN_RANK.get(o, 0):
        return n
    return o


def _pick_primary(
    confirmed: list[dict],
    candidates: list[dict],
    slot: str,
    *,
    stale: list[dict] | None = None,
) -> dict | None:
    if confirmed:
        return sorted(confirmed, key=lambda f: f.get("updated_at") or "", reverse=True)[0]
    slot_cands = [c for c in candidates if c["slot_key"] == slot]
    if slot_cands:
        return sorted(slot_cands, key=lambda f: f.get("updated_at") or "", reverse=True)[0]
    if stale:
        return sorted(stale, key=lambda f: f.get("updated_at") or "", reverse=True)[0]
    return None


def _may_overwrite(new_origin: str, old_origin: str) -> bool:
    if origin_wins_conflict(new_origin, old_origin):
        return True
    if new_origin == old_origin:
        return True
    # direct 可更新同级；inferred 不可覆盖 direct/manual
    return ORIGIN_RANK.get(new_origin, 0) >= ORIGIN_RANK.get(old_origin, 0)


def _status_after_touch(primary: dict, incoming_status: str) -> str:
    """触碰主键后的目标 status：stale 必须按合并后的抽取结果复活，不得保留 stale。"""
    if primary.get("status") == "stale":
        return incoming_status
    if incoming_status == "confirmed":
        return "confirmed"
    return primary.get("status") or incoming_status


def _apply_noop_touch(
    store: MemoryStore,
    primary: dict,
    *,
    incoming_origin: str,
    incoming_confidence: float,
) -> dict:
    """noop：可升级 origin/status、复活 stale，但不改 statement。"""
    merged_origin = _merge_origin(primary.get("origin"), incoming_origin)
    incoming_status = initial_status(merged_origin, primary.get("statement") or "")
    next_status = _status_after_touch(primary, incoming_status)
    need_update = (
        primary.get("status") == "stale"
        or merged_origin != (primary.get("origin") or "")
        or next_status != (primary.get("status") or "")
    )
    if not need_update:
        return primary
    return (
        store.update_fact_content(
            primary["id"],
            statement=primary["statement"],
            normalized_value_hash=primary["normalized_value_hash"],
            origin=merged_origin,
            confidence=max(float(primary.get("confidence") or 0), incoming_confidence),
            status=next_status,
        )
        or primary
    )
