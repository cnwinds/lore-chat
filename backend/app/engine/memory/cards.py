"""角色知识卡：按 scope（role:/persona:）读写，与主人记忆同库异 owner_key。"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from app.engine.channel_plugins.types import is_channel_origin
from app.engine.conversations import ConversationStore
from app.engine.memory.card_fade import card_fade_target
from app.engine.memory.card_growth import CardGrowthLog
from app.engine.background.purpose import llm_call_subject
from app.engine.memory.card_persona_state import CardPersonaState
from app.engine.memory.normalize import CARD_SCHEME, value_hash
from app.engine.memory.resolver import SlotAction, SlotResolver
from app.engine.memory.service import MemoryService
from app.engine.memory.store import MemoryStore
from app.engine.roles import RoleStore, VISIBILITY_HIDDEN, is_hidden_role
from app.engine.rooms.schema import KIND_OWNER_DM
from app.engine.memory.card_index import TURN_CARDS_LIMIT
from app.logging_config import get_logger

if TYPE_CHECKING:
    from app.engine.memory.card_index import CardIndex

OWNER_SCOPE = "owner"

CARD_KINDS = ("domain", "owner_context", "practice", "lesson", "audience")
EXTERNAL_KINDS = frozenset({"domain", "audience"})
KIND_LABELS = {
    "domain": "领域知识",
    "owner_context": "主人在此",
    "practice": "做法",
    "lesson": "经验",
    "audience": "受众",
}
CARD_RENDER_MAX_CHARS = 2000
RECALL_LIMIT_MAX = 10
MAX_CARDS_PER_SESSION = 6
CARD_MAINTENANCE_MIN_INTERVAL_HOURS = 24
CONSOLIDATE_SCOPES_PER_TICK = 3
EVOLVE_SCOPES_PER_TICK = 2

_PROPOSAL_REQUEST = {
    "skill": "请把下面这些经验固化为一个 Skill「{title}」：\n\n{items}\n\n（来自知识卡的升格提议：{reason}）",
    "doc": "请把下面这些内容整理成一篇文档「{title}」，存进知识库：\n\n{items}\n\n（来自知识卡的升格提议：{reason}）",
}

_log = get_logger("memory.cards")
_LEARN_GROWTH_PRIORITY = {"new": 0, "revived": 1, "promoted": 2, "revised": 3}

_ORIGIN_SORT = {
    "manual": 0,
    "direct": 1,
    "inferred": 2,
    "external": 3,
}


def role_scope(role_id: str) -> str:
    return f"role:{role_id}"


def persona_scope(persona_id: str) -> str:
    return f"persona:{persona_id}"


def parse_scope(scope: str) -> tuple[str, str]:
    raw = (scope or "").strip()
    if raw.startswith("role:") and len(raw) > 5:
        return ("role", raw[5:])
    if raw.startswith("persona:") and len(raw) > 8:
        return ("persona", raw[8:])
    raise ValueError(f"invalid card scope: {scope!r}")


@dataclass(frozen=True)
class CardLens:
    scope: str
    origin: str
    subject_name: str
    persona_text: str


@dataclass(frozen=True)
class CardInjection:
    owner_memory: str
    role_cards: str
    turn_cards: str = ""


class KnowledgeCards:
    def __init__(
        self,
        db_path: Path,
        *,
        owner: MemoryService,
        roles: RoleStore,
        conversations: ConversationStore | None = None,
        channel_instances=None,
        max_chars: int = CARD_RENDER_MAX_CHARS,
        growth: CardGrowthLog | None = None,
        consolidator=None,
        persona_state: CardPersonaState | None = None,
    ):
        self._db_path = Path(db_path)
        self.owner = owner
        self.roles = roles
        self.conversations = conversations
        self.channel_instances = channel_instances
        self.max_chars = max_chars
        self.growth = growth or CardGrowthLog(self._db_path)
        self.consolidator = consolidator
        self.owner_consolidator = None
        self.persona_state = persona_state or CardPersonaState(self._db_path)
        self.evolver = None
        self.index: CardIndex | None = None
        self.owner_index = None
        self._stores: dict[str, MemoryStore] = {}
        self._resolvers: dict[str, SlotResolver] = {}
        self._scope_locks: dict[str, threading.Lock] = {}
        self._scope_locks_guard = threading.Lock()

    @contextmanager
    def scope_lock(self, scope: str):
        with self._scope_locks_guard:
            if scope not in self._scope_locks:
                self._scope_locks[scope] = threading.Lock()
            lock = self._scope_locks[scope]
        with lock:
            yield

    def scope_for_role(self, role_id: str | None) -> str | None:
        rid = (role_id or "").strip()
        if not rid:
            return None
        try:
            role = self.roles.get(rid)
        except KeyError:
            return None
        if not is_hidden_role(role):
            return role_scope(rid)
        pid = (role.get("persona_id") or "").strip()
        if pid:
            return persona_scope(pid)
        return None

    def lenses_for(self, conversation_id: str) -> tuple[bool, CardLens | None]:
        if not self.conversations:
            return True, None
        kind = self.conversations.get_conversation_kind(conversation_id)
        origin = self.conversations.get_origin(conversation_id)
        if is_channel_origin(origin):
            persona = self._persona_for_channel(conversation_id)
            if not persona:
                return False, None
            scope, name, prompt = persona
            return False, CardLens(scope, "external", name, prompt)
        if kind == KIND_OWNER_DM:
            role_id = self.conversations.get_role_id(conversation_id)
            lens = self._direct_lens_for_role(role_id)
            return True, lens
        return False, None

    def resolve_subject(self, name_or_id: str) -> str | None:
        key = (name_or_id or "").strip()
        if not key:
            return None
        try:
            self.roles.get(key)
            return self.scope_for_role(key)
        except KeyError:
            pass
        key_lower = key.lower()
        for role in self.roles.list_all():
            if (role.get("name") or "").strip().lower() == key_lower:
                if is_hidden_role(role):
                    pid = (role.get("persona_id") or "").strip()
                    if pid:
                        return persona_scope(pid)
                    return None
                return role_scope(role["id"])
        for persona in self.roles.list_personas():
            if (persona.get("name") or "").strip().lower() == key_lower:
                return persona_scope(persona["id"])
            if persona.get("id") == key:
                return persona_scope(persona["id"])
        return None

    def store(self, scope: str) -> MemoryStore:
        if scope not in self._stores:
            self._stores[scope] = MemoryStore(self._db_path, owner_key=scope)
        return self._stores[scope]

    def resolver(self, scope: str) -> SlotResolver:
        if scope not in self._resolvers:
            self._resolvers[scope] = SlotResolver(self.store(scope), scheme=CARD_SCHEME)
        return self._resolvers[scope]

    def list_scopes(self) -> list[str]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT owner_key FROM memory_facts
                WHERE owner_key LIKE 'role:%' OR owner_key LIKE 'persona:%'
                """
            ).fetchall()
        return [r[0] for r in rows]

    def subject_for_scope(self, scope: str) -> CardLens | None:
        try:
            kind, subject_id = parse_scope(scope)
        except ValueError:
            return None
        if kind == "role":
            try:
                role = self.roles.get(subject_id)
            except KeyError:
                return None
            if role.get("visibility") == VISIBILITY_HIDDEN:
                return None
            return CardLens(
                scope,
                "direct",
                role.get("name") or subject_id,
                role.get("system_prompt") or "",
            )
        try:
            persona = self.roles.get_persona(subject_id)
        except KeyError:
            return None
        return CardLens(
            scope,
            "external",
            persona.get("name") or subject_id,
            persona.get("system_prompt") or "",
        )

    def _panel_row(
        self, st: MemoryStore, fact: dict, *, merged_ids: set[str] | None = None
    ) -> dict:
        cids = sorted(
            {
                ev["conversation_id"]
                for ev in st.list_evidence(fact["id"])
                if ev.get("conversation_id")
            }
        )
        kind = fact.get("category") or ""
        origin = fact.get("origin") or ""
        merged = fact["id"] in (merged_ids or set())
        return {
            "id": fact["id"],
            "slot_key": fact["slot_key"],
            "kind": kind,
            "statement": fact["statement"],
            "origin": origin,
            "external": origin == "external",
            "status": fact.get("status"),
            "confidence": fact.get("confidence"),
            "conversation_ids": cids,
            "updated_at": fact.get("updated_at"),
            "merged_into_persona": merged,
        }

    def list_panel(self, scope: str) -> list[dict]:
        merged_ids = self.merged_card_ids(scope)
        st = self.store(scope)
        items = [
            self._panel_row(st, f, merged_ids=merged_ids)
            for f in st.list_confirmed() + st.list_candidates()
        ]
        stale_items = [
            self._panel_row(st, f, merged_ids=merged_ids)
            for f in st.list_active_facts()
            if f.get("status") == "stale"
        ]

        def updated_at(row: dict) -> str:
            return row.get("updated_at") or ""

        confirmed = [x for x in items if x.get("status") == "confirmed"]
        candidates = [x for x in items if x.get("status") == "candidate"]
        confirmed.sort(key=updated_at, reverse=True)
        candidates.sort(key=updated_at, reverse=True)
        stale_items.sort(key=updated_at, reverse=True)
        return confirmed + candidates + stale_items

    def panel_counts(self, scope: str) -> dict:
        st = self.store(scope)
        active = st.list_confirmed() + st.list_candidates()
        stale = [f for f in st.list_active_facts() if f.get("status") == "stale"]
        return {"count": len(active), "faded_count": len(stale)}

    def learn(
        self, scope: str, actions: list[SlotAction], *, conversation_id: str
    ) -> list[dict]:
        resolver = self.resolver(scope)
        results: list[dict] = []
        with self.scope_lock(scope):
            st = self.store(scope)
            snapshot = {
                f["id"]: (f.get("status"), f.get("statement"))
                for f in st.list_active_facts()
            }
            for action in actions:
                out = resolver.apply(action, conversation_id=conversation_id)
                results.append(out)
            items = _learn_growth_items(snapshot, results)
            if items:
                self.growth.append(
                    scope, "learned", items, conversation_id=conversation_id
                )
            if any(r.get("ok") for r in results):
                self._sync_index_locked(scope)
        return results

    def learn_owner(
        self, actions: list[SlotAction], *, conversation_id: str
    ) -> list[dict]:
        resolver = self.owner.resolver
        results: list[dict] = []
        with self.scope_lock(OWNER_SCOPE):
            st = self.owner.store
            snapshot = {
                f["id"]: (f.get("status"), f.get("statement"))
                for f in st.list_active_facts()
            }
            for action in actions:
                out = resolver.apply(action, conversation_id=conversation_id)
                results.append(out)
            items = _learn_growth_items(snapshot, results)
            if items:
                self.growth.append(
                    OWNER_SCOPE, "learned", items, conversation_id=conversation_id
                )
        return results

    def _sync_index_locked(self, scope: str) -> None:
        if self.index is None:
            return
        try:
            self.index.sync_scope_locked(scope)
        except Exception as exc:  # noqa: BLE001
            _log.warning("card index sync failed scope=%s err=%s", scope, exc)

    def restore(self, scope: str, card_id: str) -> dict:
        with self.scope_lock(scope):
            st = self.store(scope)
            fact = st.get_fact(card_id)
            if not fact or fact.get("status") != "stale":
                return {
                    "ok": False,
                    "error": "invalid_status",
                    "message": "仅已淡出的卡可恢复",
                }
            st.set_status(card_id, "confirmed")
            st.set_last_seen_at(card_id)
            out = {"ok": True, "fact_id": card_id}
            self._sync_index_locked(scope)
            return out

    def growth_entries(self, scope: str, limit: int = 50) -> list[dict]:
        entries = self.growth.list(scope, limit=limit)
        for entry in entries:
            cid = entry.get("conversation_id")
            title = None
            if cid and self.conversations:
                title = self.conversations.get_title(cid)
            entry["conversation_title"] = title
            if entry.get("kind") == "proposal":
                for item in entry.get("items") or []:
                    pid = item.get("proposal_id")
                    if not pid:
                        continue
                    prop = self.persona_state.get_proposal(scope, pid)
                    item["status"] = prop["status"] if prop else "dismissed"
        return entries

    def edit(self, scope: str, card_id: str, statement: str) -> dict:
        with self.scope_lock(scope):
            out = self.resolver(scope).edit_fact(card_id, statement)
            if out.get("ok"):
                self._sync_index_locked(scope)
            return out

    def forget(self, scope: str, card_id: str) -> dict:
        with self.scope_lock(scope):
            out = self.resolver(scope).forget(fact_id=card_id)
            if out.get("ok"):
                self._sync_index_locked(scope)
            return out

    def confirm(self, scope: str, card_id: str) -> dict:
        with self.scope_lock(scope):
            out = self.resolver(scope).confirm_candidate(card_id)
            if out.get("ok"):
                self._sync_index_locked(scope)
            return out

    def reject(self, scope: str, card_id: str) -> dict:
        with self.scope_lock(scope):
            out = self.resolver(scope).reject_candidate(card_id)
            if out.get("ok"):
                self._sync_index_locked(scope)
            return out

    def render(self, scope: str) -> str:
        text, _ = self.render_with_ids(scope)
        return text

    def effective_marks(self, scope: str) -> dict[str, str]:
        facts = {f["id"]: f for f in self.store(scope).list_active_facts()}
        rows = self.persona_state.marks(scope)
        out: dict[str, str] = {}
        for cid, row in rows.items():
            fact = facts.get(cid)
            if fact is None:
                continue
            if row.get("statement_hash") == value_hash(fact.get("statement") or ""):
                out[cid] = row["state"]
        return out

    def merged_card_ids(self, scope: str) -> set[str]:
        eff = self.effective_marks(scope)
        return {cid for cid, state in eff.items() if state == "merged"}

    def render_with_ids(self, scope: str) -> tuple[str, set[str]]:
        merged = self.merged_card_ids(scope)
        facts = [
            f
            for f in self.store(scope).list_confirmed()
            if f["id"] not in merged
        ]
        if not facts:
            return "", set()
        grouped: dict[str, list[dict]] = {k: [] for k in CARD_KINDS}
        for fact in facts:
            kind = (fact.get("category") or "").strip()
            if kind in grouped:
                grouped[kind].append(fact)
        for kind in CARD_KINDS:
            grouped[kind].sort(
                key=lambda f: f.get("updated_at") or "",
                reverse=True,
            )
            grouped[kind].sort(
                key=lambda f: (
                    _ORIGIN_SORT.get(f.get("origin") or "", 99),
                    -float(f.get("confidence") or 0),
                )
            )
        lines: list[str] = []
        included: set[str] = set()
        for kind in CARD_KINDS:
            if not grouped[kind]:
                continue
            header = f"## {KIND_LABELS[kind]}"
            section_started = False
            for fact in grouped[kind]:
                stmt = fact["statement"]
                if fact.get("origin") == "external":
                    stmt = f"{stmt}（外部来源）"
                entry = f"- {stmt}"
                trial = list(lines)
                if not section_started:
                    trial.extend([header, entry])
                else:
                    trial.append(entry)
                if len("\n".join(trial)) > self.max_chars:
                    break
                if not section_started:
                    lines.append(header)
                    section_started = True
                lines.append(entry)
                included.add(fact["id"])
            if lines and len("\n".join(lines)) >= self.max_chars:
                break
        return "\n".join(lines).strip(), included

    def turn_cards(self, scope: str, query: str, *, exclude_ids: set[str]) -> str:
        if self.index is None:
            return ""
        exclude = set(exclude_ids) | self.merged_card_ids(scope)
        facts = self.index.search(
            scope,
            query,
            limit=TURN_CARDS_LIMIT,
            exclude_ids=exclude,
            mode="turn",
        )
        lines: list[str] = []
        for fact in facts:
            stmt = (fact.get("statement") or "").replace("\n", " ").replace("\r", " ")
            if fact.get("origin") == "external":
                stmt = f"{stmt}（外部来源）"
            lines.append(f"- {stmt}")
        return "\n".join(lines)

    def injection_for(
        self,
        *,
        conversation_id: str | None,
        role_id: str | None,
        query: str = "",
    ) -> CardInjection:
        scope = self.scope_for_role(role_id)
        role_cards = ""
        core_ids: set[str] = set()
        if scope:
            role_cards, core_ids = self.render_with_ids(scope)

        turn_scope = scope
        if conversation_id and self.conversations:
            origin = self.conversations.get_origin(conversation_id)
            if is_channel_origin(origin):
                _, lens = self.lenses_for(conversation_id)
                if lens:
                    turn_scope = lens.scope

        turn_exclude = core_ids if turn_scope == scope else set()
        q = (query or "").strip()
        turn_cards_text = (
            self.turn_cards(turn_scope, q, exclude_ids=turn_exclude)
            if q and turn_scope
            else ""
        )

        if conversation_id and self.conversations:
            origin = self.conversations.get_origin(conversation_id)
            if is_channel_origin(origin):
                inst_id = self.conversations.get_channel_instance_id(conversation_id)
                include_owner = False
                if inst_id and self.channel_instances:
                    try:
                        inst = self.channel_instances.get(inst_id)
                        include_owner = bool(inst.get("include_owner_memory"))
                    except KeyError:
                        include_owner = False
                owner_memory = (
                    self.owner.render_context() if include_owner else ""
                )
                return CardInjection(
                    owner_memory=owner_memory,
                    role_cards=role_cards,
                    turn_cards=turn_cards_text,
                )
        return CardInjection(
            owner_memory=self.owner.render_context(),
            role_cards=role_cards,
            turn_cards=turn_cards_text,
        )

    def recall(self, scope: str, query: str = "", limit: int = RECALL_LIMIT_MAX) -> list[dict]:
        lim = max(1, min(int(limit), RECALL_LIMIT_MAX))
        q = (query or "").strip()
        if q and self.index is not None:
            facts = self.index.search(scope, q, limit=lim, mode="recall")
        else:
            facts = self.store(scope).search_confirmed(query, limit=lim)
            if not q:
                facts = sorted(
                    facts, key=lambda f: f.get("updated_at") or "", reverse=True
                )[:lim]
        out: list[dict] = []
        for f in facts:
            origin = f.get("origin") or ""
            out.append(
                {
                    "kind": f.get("category"),
                    "statement": f["statement"],
                    "external": origin == "external",
                    "updated_at": f.get("updated_at"),
                }
            )
        return out

    def _proposal_request_text(self, scope: str, proposal: dict) -> str:
        target = proposal.get("target") or "skill"
        template = _PROPOSAL_REQUEST.get(target) or _PROPOSAL_REQUEST["skill"]
        active = {f["id"]: f for f in self.store(scope).list_active_facts()}
        lines: list[str] = []
        for item in proposal.get("basis") or []:
            cid = item.get("card_id") or ""
            stmt = item.get("statement") or ""
            fact = active.get(cid)
            if fact:
                stmt = fact.get("statement") or stmt
            lines.append(f"- {stmt}")
        items = "\n".join(lines)
        return template.format(
            title=proposal.get("title") or "",
            items=items,
            reason=proposal.get("reason") or "",
        )

    def accept_proposal(self, scope: str, proposal_id: str) -> dict:
        prop = self.persona_state.get_proposal(scope, proposal_id)
        if prop is None:
            return {"ok": False, "error": "not_found"}
        if prop.get("status") != "pending":
            return {"ok": False, "error": "invalid_status"}
        decided = self.persona_state.decide_proposal(scope, proposal_id, "accepted")
        if decided is None:
            return {"ok": False, "error": "invalid_status"}
        text = self._proposal_request_text(scope, decided)
        return {"ok": True, "request_text": text}

    def dismiss_proposal(self, scope: str, proposal_id: str) -> dict:
        prop = self.persona_state.get_proposal(scope, proposal_id)
        if prop is None:
            return {"ok": False, "error": "not_found"}
        if prop.get("status") != "pending":
            return {"ok": False, "error": "invalid_status"}
        self.persona_state.decide_proposal(scope, proposal_id, "dismissed")
        return {"ok": True}

    def purge_scope(self, scope: str) -> int:
        n = self.store(scope).purge_owner()
        self.growth.purge(scope)
        self.persona_state.purge(scope)
        self._stores.pop(scope, None)
        self._resolvers.pop(scope, None)
        if self.index is not None:
            try:
                self.index.drop_scope(scope)
            except Exception as exc:  # noqa: BLE001
                _log.warning("card index drop failed scope=%s err=%s", scope, exc)
        blog = getattr(self, "background_call_log", None)
        if blog is not None:
            try:
                blog.delete_scope(scope)
            except Exception:
                _log.exception("background call log purge scope=%s", scope)
        return n

    def maintain(
        self,
        *,
        now: datetime | None = None,
        max_consolidations: int = CONSOLIDATE_SCOPES_PER_TICK,
        paused: frozenset[str] = frozenset(),
    ) -> dict:
        stamp = now or datetime.now(timezone.utc)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        faded_total = 0
        consolidated_scopes = 0
        ops_applied = 0
        evolved_scopes = 0
        min_gap = timedelta(hours=CARD_MAINTENANCE_MIN_INTERVAL_HOURS)
        evolve_budget = EVOLVE_SCOPES_PER_TICK
        skip_consolidate = "consolidation" in paused
        skip_evolve = "persona_evolution" in paused

        if not skip_consolidate:
            consolidated_scopes, ops_delta = self._maybe_consolidate_owner(
                stamp, min_gap, consolidated_scopes, max_consolidations
            )
            ops_applied += ops_delta

        for scope in self.list_scopes():
            try:
                lens = self.subject_for_scope(scope)
                if lens is None:
                    continue
                state = self.growth.scope_state(scope)
                faded_total += self._maybe_fade(scope, stamp, state, min_gap)
                if not skip_consolidate:
                    consolidated_scopes, ops_delta = self._maybe_consolidate(
                        scope,
                        stamp,
                        state,
                        min_gap,
                        lens,
                        consolidated_scopes,
                        max_consolidations,
                    )
                    ops_applied += ops_delta
                if not skip_evolve:
                    evolved_scopes += self._maybe_evolve(
                        scope,
                        stamp,
                        state,
                        min_gap,
                        lens,
                        evolve_budget - evolved_scopes,
                    )
            except Exception as exc:  # noqa: BLE001
                _log.warning("card maintain failed scope=%s err=%s", scope, exc)

        if self.index is not None:
            try:
                self.index.sync_all()
            except Exception as exc:  # noqa: BLE001
                _log.warning("card index sync_all failed err=%s", exc)
        owner_idx = self.owner_index
        if owner_idx is not None:
            try:
                owner_idx.sync()
            except Exception as exc:  # noqa: BLE001
                _log.warning("owner index sync failed err=%s", exc)

        return {
            "faded": faded_total,
            "consolidated_scopes": consolidated_scopes,
            "ops_applied": ops_applied,
            "evolved_scopes": evolved_scopes,
        }

    def _maybe_fade(
        self,
        scope: str,
        stamp: datetime,
        state: dict,
        min_gap: timedelta,
    ) -> int:
        last_faded = state.get("last_faded_at")
        if last_faded and stamp - self._parse_ts(last_faded) < min_gap:
            return 0
        items = self._fade_scope(scope, now=stamp)
        if items:
            self.growth.append(scope, "faded", items)
        self.growth.mark_faded(scope, stamp.isoformat())
        return len(items)

    def _maybe_consolidate_owner(
        self,
        stamp: datetime,
        min_gap: timedelta,
        consolidated_scopes: int,
        max_consolidations: int,
    ) -> tuple[int, int]:
        if consolidated_scopes >= max_consolidations:
            return consolidated_scopes, 0
        if not self.owner_consolidator:
            return consolidated_scopes, 0
        state = self.growth.scope_state(OWNER_SCOPE)
        last_cons = state.get("last_consolidated_at")
        if last_cons and stamp - self._parse_ts(last_cons) < min_gap:
            return consolidated_scopes, 0
        st = self.owner.store
        active = st.list_confirmed() + st.list_candidates()
        if len(active) < 2:
            return consolidated_scopes, 0
        if last_cons and not self._has_card_changes_since(st, active, last_cons):
            return consolidated_scopes, 0
        try:
            with llm_call_subject(scope=OWNER_SCOPE):
                result = self.owner_consolidator.run(OWNER_SCOPE, None)
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "owner memory consolidation failed err=%s", exc
            )
            return consolidated_scopes, 0
        consolidated_at = max(stamp, datetime.now(timezone.utc)).isoformat()
        self.growth.mark_consolidated(OWNER_SCOPE, consolidated_at)
        return consolidated_scopes + 1, int(result.get("ops_applied") or 0)

    def _maybe_consolidate(
        self,
        scope: str,
        stamp: datetime,
        state: dict,
        min_gap: timedelta,
        lens: CardLens,
        consolidated_scopes: int,
        max_consolidations: int,
    ) -> tuple[int, int]:
        if consolidated_scopes >= max_consolidations:
            return consolidated_scopes, 0
        if not self.consolidator:
            return consolidated_scopes, 0
        last_cons = state.get("last_consolidated_at")
        if last_cons and stamp - self._parse_ts(last_cons) < min_gap:
            return consolidated_scopes, 0
        st = self.store(scope)
        active = st.list_confirmed() + st.list_candidates()
        if len(active) < 2:
            return consolidated_scopes, 0
        if last_cons and not self._has_card_changes_since(st, active, last_cons):
            return consolidated_scopes, 0
        try:
            with llm_call_subject(scope=scope):
                result = self.consolidator.run(scope, lens)
        except Exception as exc:  # noqa: BLE001
            _log.warning("card consolidation failed scope=%s err=%s", scope, exc)
            return consolidated_scopes, 0
        consolidated_at = max(stamp, datetime.now(timezone.utc)).isoformat()
        self.growth.mark_consolidated(scope, consolidated_at)
        with self.scope_lock(scope):
            self._sync_index_locked(scope)
        return consolidated_scopes + 1, int(result.get("ops_applied") or 0)

    def _maybe_evolve(
        self,
        scope: str,
        stamp: datetime,
        state: dict,
        min_gap: timedelta,
        lens: CardLens,
        budget: int,
    ) -> int:
        if budget <= 0 or self.evolver is None:
            return 0
        last_ev = state.get("last_evolved_at")
        if last_ev and stamp - self._parse_ts(last_ev) < min_gap:
            return 0
        if not self.evolver.should_run(scope):
            return 0
        try:
            with llm_call_subject(scope=scope):
                result = self.evolver.run(scope, lens)
        except Exception as exc:  # noqa: BLE001
            _log.warning("persona evolution failed scope=%s err=%s", scope, exc)
            return 0
        if result.get("skipped") == "onboarding" or result.get("aborted"):
            return 0
        self.growth.mark_evolved(scope, stamp.isoformat())
        return 1

    def _fade_scope(self, scope: str, *, now: datetime) -> list[dict]:
        items: list[dict] = []
        with self.scope_lock(scope):
            st = self.store(scope)
            for fact in st.list_confirmed() + st.list_candidates():
                target = card_fade_target(fact, now=now)
                if not target:
                    continue
                if target == "stale":
                    st.set_status(fact["id"], "stale")
                    items.append(
                        {
                            "action": "expired",
                            "card_id": fact["id"],
                            "kind": fact.get("category") or "",
                            "statement": fact.get("statement") or "",
                            "external": (fact.get("origin") or "") == "external",
                            "status": "stale",
                        }
                    )
                elif target == "rejected":
                    st.set_status(fact["id"], "rejected")
                    items.append(
                        {
                            "action": "dropped",
                            "card_id": fact["id"],
                            "kind": fact.get("category") or "",
                            "statement": fact.get("statement") or "",
                            "external": (fact.get("origin") or "") == "external",
                            "status": "rejected",
                        }
                    )
            if items:
                self._sync_index_locked(scope)
        return items

    @staticmethod
    def _parse_ts(raw: str) -> datetime:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    @staticmethod
    def _has_card_changes_since(
        st: MemoryStore, active: list[dict], last_consolidated_at: str
    ) -> bool:
        for fact in active:
            for field in ("created_at", "updated_at"):
                ts = fact.get(field)
                if ts and ts > last_consolidated_at:
                    return True
        return False

    def _direct_lens_for_role(self, role_id: str) -> CardLens | None:
        scope = self.scope_for_role(role_id)
        if not scope:
            return None
        try:
            role = self.roles.get(role_id)
        except KeyError:
            return None
        return CardLens(
            scope,
            "direct",
            role.get("name") or role_id,
            role.get("system_prompt") or "",
        )

    def _persona_for_channel(
        self, conversation_id: str
    ) -> tuple[str, str, str] | None:
        if not self.conversations:
            return None
        inst_id = self.conversations.get_channel_instance_id(conversation_id)
        if not inst_id or not self.channel_instances:
            return None
        try:
            inst = self.channel_instances.get(inst_id)
        except KeyError:
            return None
        pid = (inst.get("persona_id") or "").strip()
        if not pid:
            return None
        try:
            persona = self.roles.get_persona(pid)
        except KeyError:
            return None
        scope = persona_scope(pid)
        return (
            scope,
            persona.get("name") or pid,
            persona.get("system_prompt") or "",
        )


def _learn_growth_items(
    snapshot: dict[str, tuple],
    results: list[dict],
) -> list[dict]:
    growth_by_id: dict[str, dict] = {}
    for out in results:
        if not out.get("ok"):
            continue
        fact = out.get("fact") or {}
        fid = fact.get("id")
        if not fid:
            continue
        snap = snapshot.get(fid)
        growth_action: str | None = None
        previous: str | None = None
        if snap is None:
            growth_action = "new"
        else:
            old_status, old_stmt = snap
            new_status = fact.get("status")
            new_stmt = fact.get("statement")
            if old_status == "stale" and new_status in ("confirmed", "candidate"):
                growth_action = "revived"
            elif old_status == "candidate" and new_status == "confirmed":
                growth_action = "promoted"
            elif old_stmt != new_stmt:
                growth_action = "revised"
                previous = old_stmt
            else:
                continue
        existing = growth_by_id.get(fid)
        if existing:
            old_prio = _LEARN_GROWTH_PRIORITY.get(existing["action"], 99)
            new_prio = _LEARN_GROWTH_PRIORITY.get(growth_action or "", 99)
            if new_prio >= old_prio:
                continue
        item = {
            "action": growth_action,
            "card_id": fid,
            "kind": fact.get("category") or "",
            "statement": fact.get("statement") or "",
            "external": (fact.get("origin") or "") == "external",
            "status": fact.get("status") or "",
        }
        if previous:
            item["previous"] = previous
        growth_by_id[fid] = item
    return list(growth_by_id.values())
