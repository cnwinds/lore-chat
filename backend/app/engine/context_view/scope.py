from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.engine.channel_plugins.types import is_channel_origin
from app.engine.context_view.errors import AmbiguousSubject, InvalidUri, NotFound, OutOfScope
from app.engine.context_view.uri import (
    ConversationRoot,
    ConversationUri,
    KbUri,
    LegacyConversationRef,
    LoreRoot,
    LoreUri,
    MemoryRoot,
    MemoryUri,
    format_uri,
    is_kb_internal,
    parse,
    uri_covers,
    uri_path_key,
)
from app.engine.conversations import ConversationStore
from app.engine.memory.cards import KnowledgeCards
from app.engine.roles import DEFAULT_ROLE_ID, RoleStore, is_api_role_id, list_sidebar_roles
from app.engine.rooms.schema import KIND_GROUP, KIND_OWNER_DM, KIND_PEER_DM

TurnKind = Literal["owner", "channel"]

TILDE = "~"


@dataclass
class ViewScope:
    """本回合可见的 lore:// 视图范围。"""

    conversations: ConversationStore
    roles: RoleStore
    cards: KnowledgeCards
    channel_instances: object | None
    conversation_id: str | None
    responding_role_id: str
    turn_kind: TurnKind
    channel_instance_id: str | None
    channel_persona_id: str | None
    include_owner_memory: bool

    @classmethod
    def build(
        cls,
        *,
        conversations: ConversationStore,
        roles: RoleStore,
        cards: KnowledgeCards,
        channel_instances: object | None = None,
        conversation_id: str | None = None,
        responding_role_id: str | None = None,
    ) -> ViewScope:
        cid = (conversation_id or "").strip() or None
        rid = (responding_role_id or "").strip()
        if not rid and cid:
            rid = conversations.get_role_id(cid)
        if not rid:
            rid = DEFAULT_ROLE_ID
        turn: TurnKind = "owner"
        inst_id: str | None = None
        persona_id: str | None = None
        include_owner = True
        if cid:
            origin = conversations.get_origin(cid)
            if is_channel_origin(origin):
                turn = "channel"
                inst_id = conversations.get_channel_instance_id(cid)
                persona_id = cls._persona_id_for_instance(
                    channel_instances, inst_id
                )
                include_owner = cls._include_owner_memory(
                    channel_instances, inst_id
                )
        return cls(
            conversations=conversations,
            roles=roles,
            cards=cards,
            channel_instances=channel_instances,
            conversation_id=cid,
            responding_role_id=rid,
            turn_kind=turn,
            channel_instance_id=inst_id,
            channel_persona_id=persona_id,
            include_owner_memory=include_owner,
        )

    @staticmethod
    def _persona_id_for_instance(store: object | None, inst_id: str | None) -> str | None:
        iid = (inst_id or "").strip()
        if not iid or store is None:
            return None
        try:
            inst = store.get(iid)  # type: ignore[union-attr]
        except KeyError:
            return None
        pid = (inst.get("persona_id") or "").strip()
        return pid or None

    @staticmethod
    def _include_owner_memory(store: object | None, inst_id: str | None) -> bool:
        iid = (inst_id or "").strip()
        if not iid or store is None:
            return False
        try:
            inst = store.get(iid)  # type: ignore[union-attr]
        except KeyError:
            return False
        return bool(inst.get("include_owner_memory"))

    @property
    def current_conversation_id(self) -> str | None:
        return self.conversation_id

    def visible_sidebar_role_ids(self) -> list[str]:
        return [r["id"] for r in list_sidebar_roles(self.roles)]

    def _resolve_role_segment(self, segment: str, *, for_persona: bool) -> str:
        if segment == TILDE:
            if for_persona:
                if self.turn_kind == "channel" and self.channel_persona_id:
                    return self.channel_persona_id
                raise InvalidUri("非通道回合不可用 memory/persona/~")
            return self.responding_role_id
        if for_persona:
            return self._resolve_persona_subject(segment)
        return self._resolve_role_subject(segment)

    def _resolve_role_subject(self, segment: str) -> str:
        key = (segment or "").strip()
        if not key:
            raise InvalidUri("缺少角色 id")
        try:
            role = self.roles.get(key)
        except KeyError:
            role = None
        if role is not None:
            if is_api_role_id(role["id"]):
                raise NotFound("隐藏工作角色不在 dm/ 或 memory/role/ 视图中", uri=key)
            return role["id"]
        matches = self._roles_matching_name(key)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise AmbiguousSubject(f"角色名不唯一: {key}", uri=key)
        raise NotFound(f"未知角色: {key}", uri=key)

    def _resolve_persona_subject(self, segment: str) -> str:
        key = (segment or "").strip()
        if not key:
            raise InvalidUri("缺少人设 id")
        try:
            persona = self.roles.get_persona(key)
            return persona["id"]
        except KeyError:
            pass
        key_lower = key.lower()
        visible_ids = self._visible_persona_ids()
        matches: list[str] = []
        for pid in visible_ids:
            try:
                p = self.roles.get_persona(pid)
            except KeyError:
                continue
            name = (p.get("name") or "").strip().lower()
            if name == key_lower or pid == key:
                matches.append(pid)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise AmbiguousSubject(f"人设名不唯一: {key}", uri=key)
        raise NotFound(f"未知或不可见人设: {key}", uri=key)

    def _visible_persona_ids(self) -> list[str]:
        if self.turn_kind == "channel":
            if self.channel_persona_id:
                return [self.channel_persona_id]
            return []
        return [p["id"] for p in self.roles.list_personas()]

    def _roles_matching_name(self, name: str) -> list[str]:
        key_lower = name.lower()
        out: list[str] = []
        for rid in self.visible_sidebar_role_ids():
            try:
                role = self.roles.get(rid)
            except KeyError:
                continue
            rname = (role.get("name") or "").strip().lower()
            if rname == key_lower:
                out.append(rid)
        return out

    def conversation_bucket(self, cid: str) -> tuple[str, str | None]:
        """返回 (bucket, owner)：dm 的 owner 为 stored role_id，channels 为 instance id。"""
        row = self.conversations.get_conversation_row(cid)
        kind = row["kind"]
        origin = row["origin"]
        if is_channel_origin(origin):
            inst = row["channel_instance_id"]
            if not inst:
                raise NotFound(f"通道会话缺少实例 id: {cid}", uri=cid)
            return ("channels", inst)
        if kind in (KIND_PEER_DM, KIND_GROUP):
            return ("rooms", None)
        if kind == KIND_OWNER_DM:
            role_id = row["role_id"]
            if is_api_role_id(role_id):
                raise NotFound(f"隐藏角色私聊不在 dm/ 视图: {cid}", uri=cid)
            return ("dm", role_id)
        return ("rooms", None)

    def resolve(self, uri_or_str: str | LoreUri | LegacyConversationRef) -> LoreUri:
        if isinstance(uri_or_str, (LoreRoot, KbUri, ConversationUri, MemoryUri)):
            parsed: LoreUri | LegacyConversationRef = uri_or_str
        else:
            parsed = parse(str(uri_or_str))
        if isinstance(parsed, LegacyConversationRef):
            return self._legacy_to_canonical(parsed)
        if isinstance(parsed, (ConversationRoot, MemoryRoot)):
            return parsed
        if isinstance(parsed, ConversationUri):
            return self._resolve_conversation_uri(parsed)
        if isinstance(parsed, MemoryUri):
            return self._resolve_memory_uri(parsed)
        if isinstance(parsed, KbUri):
            _reject_internal_kb_path(parsed.rel_path)
            return parsed
        return parsed

    def _legacy_to_canonical(self, ref: LegacyConversationRef) -> ConversationUri:
        cid = ref.conversation_id
        try:
            bucket, owner = self.conversation_bucket(cid)
        except KeyError:
            raise NotFound(f"未知会话: {cid}", uri=cid) from None
        return ConversationUri(
            bucket=bucket,  # type: ignore[arg-type]
            owner=owner,
            conversation_id=cid,
            message_id=ref.message_id,
            is_dir=ref.message_id is None,
        )

    def _resolve_conversation_uri(self, uri: ConversationUri) -> ConversationUri:
        owner = uri.owner
        if uri.bucket == "dm" and owner:
            owner = self._resolve_role_segment(owner, for_persona=False)
        elif uri.bucket == "channels" and owner:
            owner = (owner or "").strip()
            if owner == TILDE and self.channel_instance_id:
                owner = self.channel_instance_id
            elif owner == TILDE:
                raise InvalidUri("channels 路径不支持 ~")
        return ConversationUri(
            uri.bucket,
            owner,
            uri.conversation_id,
            uri.message_id,
            uri.is_dir,
        )

    def _resolve_memory_uri(self, uri: MemoryUri) -> MemoryUri:
        subject = uri.subject
        if uri.scope_kind == "role" and subject:
            subject = self._resolve_role_segment(subject, for_persona=False)
            if is_api_role_id(subject):
                raise NotFound("隐藏工作角色无 memory/role/ 视图", uri=subject)
        elif uri.scope_kind == "persona" and subject:
            subject = self._resolve_role_segment(subject, for_persona=True)
        if uri.scope_kind == "persona" and self.turn_kind == "channel":
            visible = self._visible_persona_ids()
            if subject and subject not in visible:
                raise OutOfScope(format_uri(uri))
        return MemoryUri(
            uri.scope_kind,
            subject,
            uri.kind,
            uri.item_id,
            uri.is_dir,
        )

    def check(self, uri: LoreUri) -> None:
        """落在可见根内；会话 URI 校验桶归属，不匹配为 NotFound。"""
        roots = self.visible_roots()
        if isinstance(uri, ConversationRoot):
            if not any(isinstance(r, ConversationUri) for r in roots):
                raise OutOfScope(format_uri(uri))
            return
        if isinstance(uri, MemoryRoot):
            if not any(isinstance(r, MemoryUri) for r in roots):
                raise OutOfScope(format_uri(uri))
            return
        if isinstance(uri, LoreRoot):
            return
        if not any(uri_covers(root, uri) or _same_uri(root, uri) for root in roots):
            raise OutOfScope(format_uri(uri))
        if isinstance(uri, ConversationUri):
            self._check_conversation_uri(uri)
        if isinstance(uri, MemoryUri):
            self._check_memory_uri(uri)
        if isinstance(uri, KbUri):
            _reject_internal_kb_path(uri.rel_path)

    def _check_conversation_uri(self, uri: ConversationUri) -> None:
        if self.turn_kind == "channel" and uri.bucket in ("dm", "rooms"):
            raise OutOfScope(format_uri(uri))
        if self.turn_kind == "owner" and uri.bucket == "channels":
            raise OutOfScope(format_uri(uri))
        if not uri.conversation_id:
            if uri.bucket == "dm" and uri.owner:
                if uri.owner not in self.visible_sidebar_role_ids():
                    raise OutOfScope(format_uri(uri))
            if uri.bucket == "channels":
                if self.turn_kind == "channel":
                    raise OutOfScope(format_uri(uri))
                if uri.owner and uri.owner != self.channel_instance_id:
                    raise NotFound("实例 id 与当前通道不符", uri=format_uri(uri))
            return
        cid = uri.conversation_id
        try:
            bucket, owner = self.conversation_bucket(cid)
        except KeyError:
            raise NotFound(f"未知会话: {cid}", uri=format_uri(uri)) from None
        if uri.bucket != bucket:
            raise NotFound("会话与路径桶不一致", uri=format_uri(uri))
        if bucket in ("dm", "channels") and uri.owner and owner != uri.owner:
            raise NotFound("会话与路径归属不一致", uri=format_uri(uri))
        if self.turn_kind == "channel":
            if bucket != "channels" or cid != self.conversation_id:
                raise OutOfScope(format_uri(uri))

    def _check_memory_uri(self, uri: MemoryUri) -> None:
        if uri.scope_kind == "owner":
            if self.turn_kind == "channel" and not self.include_owner_memory:
                raise OutOfScope(format_uri(uri))
            return
        if uri.scope_kind == "role":
            if self.turn_kind == "channel":
                raise OutOfScope(format_uri(uri))
            if uri.subject and uri.subject not in self.visible_sidebar_role_ids():
                raise OutOfScope(format_uri(uri))
            return
        if uri.scope_kind == "persona":
            visible = self._visible_persona_ids()
            if self.turn_kind == "channel":
                if not visible:
                    raise OutOfScope(format_uri(uri))
            if uri.subject and uri.subject not in visible:
                raise OutOfScope(format_uri(uri))

    def visible_roots(self) -> list[LoreUri]:
        roots: list[LoreUri] = [KbUri("", True)]
        if self.turn_kind == "owner":
            roots.append(ConversationUri("dm", None, None, None, True))
            roots.append(ConversationUri("rooms", None, None, None, True))
            roots.append(MemoryUri("owner", None, None, None, True))
            roots.append(MemoryUri("role", None, None, None, True))
            roots.append(MemoryUri("persona", None, None, None, True))
            for rid in self.visible_sidebar_role_ids():
                roots.append(
                    ConversationUri("dm", rid, None, None, True)
                )
                roots.append(MemoryUri("role", rid, None, None, True))
            for pid in self._visible_persona_ids():
                roots.append(MemoryUri("persona", pid, None, None, True))
        else:
            if self.conversation_id and self.channel_instance_id:
                roots.append(
                    ConversationUri(
                        "channels",
                        self.channel_instance_id,
                        self.conversation_id,
                        None,
                        True,
                    )
                )
            if self.include_owner_memory:
                roots.append(MemoryUri("owner", None, None, None, True))
            if self._visible_persona_ids():
                roots.append(MemoryUri("persona", None, None, None, True))
            for pid in self._visible_persona_ids():
                roots.append(MemoryUri("persona", pid, None, None, True))
        return roots

    def default_search_paths(self) -> list[str]:
        if self.turn_kind == "channel":
            return ["lore://kb/"]
        return [
            "lore://kb/",
            f"lore://conversations/dm/{self.responding_role_id}/",
        ]

    def resolve_and_check(self, uri_or_str: str) -> LoreUri:
        uri = self.resolve(uri_or_str)
        self.check(uri)
        return uri


def _same_uri(a: LoreUri, b: LoreUri) -> bool:
    return uri_path_key(a) == uri_path_key(b)


def _reject_internal_kb_path(rel_path: str) -> None:
    if is_kb_internal(rel_path):
        raise InvalidUri("知识库内部路径不可访问", uri=rel_path)
