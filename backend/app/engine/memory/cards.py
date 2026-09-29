"""角色知识卡：按 scope（role:/persona:）读写，与主人记忆同库异 owner_key。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.engine.channel_plugins.types import is_channel_origin
from app.engine.conversations import ConversationStore
from app.engine.memory.normalize import CARD_SCHEME
from app.engine.memory.resolver import SlotResolver
from app.engine.memory.service import MemoryService
from app.engine.memory.store import MemoryStore
from app.engine.roles import RoleStore, is_hidden_role
from app.engine.rooms.schema import KIND_OWNER_DM

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
    ):
        self._db_path = Path(db_path)
        self.owner = owner
        self.roles = roles
        self.conversations = conversations
        self.channel_instances = channel_instances
        self.max_chars = max_chars
        self._stores: dict[str, MemoryStore] = {}
        self._resolvers: dict[str, SlotResolver] = {}

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

    def list_panel(self, scope: str) -> list[dict]:
        st = self.store(scope)
        items: list[dict] = []
        for f in st.list_confirmed() + st.list_candidates():
            cids = sorted(
                {
                    ev["conversation_id"]
                    for ev in st.list_evidence(f["id"])
                    if ev.get("conversation_id")
                }
            )
            kind = f.get("category") or ""
            origin = f.get("origin") or ""
            items.append(
                {
                    "id": f["id"],
                    "slot_key": f["slot_key"],
                    "kind": kind,
                    "statement": f["statement"],
                    "origin": origin,
                    "external": origin == "external",
                    "status": f.get("status"),
                    "confidence": f.get("confidence"),
                    "conversation_ids": cids,
                    "updated_at": f.get("updated_at"),
                }
            )

        def updated_at(row: dict) -> str:
            return row.get("updated_at") or ""

        confirmed = [x for x in items if x.get("status") == "confirmed"]
        candidates = [x for x in items if x.get("status") == "candidate"]
        confirmed.sort(key=updated_at, reverse=True)
        candidates.sort(key=updated_at, reverse=True)
        return confirmed + candidates

    def edit(self, scope: str, card_id: str, statement: str) -> dict:
        return self.resolver(scope).edit_fact(card_id, statement)

    def forget(self, scope: str, card_id: str) -> dict:
        return self.resolver(scope).forget(fact_id=card_id)

    def confirm(self, scope: str, card_id: str) -> dict:
        return self.resolver(scope).confirm_candidate(card_id)

    def reject(self, scope: str, card_id: str) -> dict:
        return self.resolver(scope).reject_candidate(card_id)

    def render(self, scope: str) -> str:
        facts = self.store(scope).list_confirmed()
        if not facts:
            return ""
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
            if lines and len("\n".join(lines)) >= self.max_chars:
                break
        return "\n".join(lines).strip()

    def injection_for(
        self,
        *,
        conversation_id: str | None,
        role_id: str | None,
    ) -> CardInjection:
        scope = self.scope_for_role(role_id)
        role_cards = self.render(scope) if scope else ""
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
                return CardInjection(owner_memory=owner_memory, role_cards=role_cards)
        return CardInjection(
            owner_memory=self.owner.render_context(),
            role_cards=role_cards,
        )

    def recall(self, scope: str, query: str = "", limit: int = RECALL_LIMIT_MAX) -> list[dict]:
        lim = max(1, min(int(limit), RECALL_LIMIT_MAX))
        facts = self.store(scope).search_confirmed(query, limit=lim)
        if not query.strip():
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

    def purge_scope(self, scope: str) -> int:
        n = self.store(scope).purge_owner()
        self._stores.pop(scope, None)
        self._resolvers.pop(scope, None)
        return n

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
