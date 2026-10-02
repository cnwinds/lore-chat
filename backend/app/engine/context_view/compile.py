from __future__ import annotations

from dataclasses import dataclass, field

from app.engine.context_view.errors import InvalidUri
from app.engine.context_view.scope import ViewScope
from app.engine.context_view.uri import (
    ConversationRoot,
    ConversationUri,
    KbUri,
    LoreUri,
    MemoryRoot,
    MemoryUri,
    format_uri,
    uri_covers,
)
from app.engine.memory.cards import persona_scope, role_scope

MAX_COMPILE_PATHS = 8


@dataclass
class SearchPlan:
    search_kb: bool = False
    kb_prefixes: list[str] | None = None  # 仅 search_kb 时有意义；None = 整库
    search_conversations: bool = False
    conversation_ids: list[str] = field(default_factory=list)
    include_current_conversation: bool = False
    memory_targets: list[tuple[str, str | None]] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)


def compile_search(
    scope: ViewScope,
    uris: list[str | LoreUri],
) -> SearchPlan:
    if len(uris) > MAX_COMPILE_PATHS:
        raise InvalidUri(f"检索路径最多 {MAX_COMPILE_PATHS} 条")
    resolved: list[LoreUri] = []
    for item in uris:
        if isinstance(item, str):
            u = scope.resolve_and_check(item)
        else:
            u = scope.resolve(item)
            scope.check(u)
        resolved.append(u)
    resolved = _dedupe_nested(resolved)
    plan = SearchPlan(paths=[format_uri(u) for u in resolved])
    kb_prefixes: list[str] = []
    kb_whole = False
    conv_ids: set[str] = set()
    saw_conversation_uri = False
    explicit_current = False
    memory: list[tuple[str, str | None]] = []
    current_cid = scope.current_conversation_id

    for uri in resolved:
        if isinstance(uri, KbUri):
            if not uri.rel_path and uri.is_dir:
                kb_whole = True
            else:
                prefix = uri.rel_path.replace("\\", "/")
                if uri.is_dir:
                    prefix = prefix.rstrip("/") + "/"
                kb_prefixes.append(prefix)
        elif isinstance(uri, ConversationRoot):
            saw_conversation_uri = True
            ids, _ = _conversation_ids_from_root(scope)
            conv_ids.update(ids)
        elif isinstance(uri, ConversationUri):
            saw_conversation_uri = True
            ids, names_current = _conversation_ids(scope, uri)
            conv_ids.update(ids)
            if names_current:
                explicit_current = True
        elif isinstance(uri, MemoryRoot):
            memory.extend(_memory_targets_from_root(scope))
        elif isinstance(uri, MemoryUri):
            memory.extend(_memory_targets(scope, uri))

    if kb_whole:
        plan.search_kb = True
        plan.kb_prefixes = None
    elif kb_prefixes:
        plan.search_kb = True
        plan.kb_prefixes = list(dict.fromkeys(kb_prefixes))
    else:
        plan.search_kb = False
        plan.kb_prefixes = None

    if saw_conversation_uri:
        plan.search_conversations = True
        if current_cid and not explicit_current:
            conv_ids.discard(current_cid)
        plan.conversation_ids = sorted(conv_ids)
        plan.include_current_conversation = bool(
            explicit_current and current_cid and current_cid in conv_ids
        )
    else:
        plan.search_conversations = False
        plan.conversation_ids = []
        plan.include_current_conversation = False

    plan.memory_targets = _dedupe_memory(memory)
    return plan


def _memory_targets_from_root(scope: ViewScope) -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    if scope.turn_kind == "owner" or scope.include_owner_memory:
        out.append(("owner", None))
    if scope.turn_kind == "owner":
        for rid in scope.visible_sidebar_role_ids():
            out.append((role_scope(rid), None))
    for pid in scope._visible_persona_ids():
        out.append((persona_scope(pid), None))
    return out


def _conversation_ids_from_root(scope: ViewScope) -> tuple[set[str], bool]:
    if scope.turn_kind == "channel":
        cid = scope.current_conversation_id
        return ({cid} if cid else set()), bool(cid)
    ids: set[str] = set()
    for rid in scope.visible_sidebar_role_ids():
        ids.update(scope.conversations.list_owner_dm_conversation_ids_for_role(rid))
    ids.update(scope.conversations.list_room_conversation_ids())
    return ids, False


def _dedupe_nested(uris: list[LoreUri]) -> list[LoreUri]:
    if not uris:
        return []
    keep: list[LoreUri] = []
    for i, outer in enumerate(uris):
        if any(i != j and uri_covers(other, outer) for j, other in enumerate(uris)):
            continue
        keep.append(outer)
    return keep


def _conversation_ids(
    scope: ViewScope, uri: ConversationUri
) -> tuple[set[str], bool]:
    """返回会话 id 集合，以及该 URI 是否显式点名当前会话（含消息 URI）。"""
    current_cid = scope.current_conversation_id
    if uri.conversation_id:
        ids = {uri.conversation_id}
        names_current = bool(current_cid and uri.conversation_id == current_cid)
        return ids, names_current
    if uri.bucket == "dm":
        if not uri.owner:
            ids: set[str] = set()
            for rid in scope.visible_sidebar_role_ids():
                ids.update(
                    scope.conversations.list_owner_dm_conversation_ids_for_role(rid)
                )
            return ids, False
        return set(
            scope.conversations.list_owner_dm_conversation_ids_for_role(uri.owner)
        ), False
    if uri.bucket == "rooms":
        return set(scope.conversations.list_room_conversation_ids()), False
    if uri.bucket == "channels":
        return set(), False
    return set(), False


def _memory_targets(
    scope: ViewScope, uri: MemoryUri
) -> list[tuple[str, str | None]]:
    kind_filter = uri.kind if uri.kind else None
    if uri.scope_kind == "owner":
        return [("owner", kind_filter)]
    if uri.scope_kind == "role":
        if uri.subject:
            return [(role_scope(uri.subject), kind_filter)]
        return [
            (role_scope(rid), kind_filter)
            for rid in scope.visible_sidebar_role_ids()
        ]
    if uri.subject:
        return [(persona_scope(uri.subject), kind_filter)]
    return [
        (persona_scope(pid), kind_filter) for pid in scope._visible_persona_ids()
    ]


def _dedupe_memory(
    items: list[tuple[str, str | None]],
) -> list[tuple[str, str | None]]:
    seen: set[tuple[str, str | None]] = set()
    out: list[tuple[str, str | None]] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out
