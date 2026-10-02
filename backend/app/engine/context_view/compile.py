from __future__ import annotations

from dataclasses import dataclass, field

from app.engine.context_view.errors import InvalidUri
from app.engine.context_view.scope import ViewScope
from app.engine.context_view.uri import (
    ConversationUri,
    KbUri,
    LoreUri,
    MemoryUri,
    format_uri,
    parse,
    uri_covers,
    uri_path_key,
)
from app.engine.memory.cards import persona_scope, role_scope

MAX_COMPILE_PATHS = 8

# kb_prefixes 中 ``""`` 表示整库 ``kb:main``（等价于 lore://kb/）。
KB_WHOLE_PREFIX = ""


@dataclass
class SearchPlan:
    kb_prefixes: list[str] | None = None
    kb_all: bool = False
    conversation_ids: list[str] | None = None
    include_current_conversation: bool = False
    memory_targets: list[tuple[str, str | None]] = field(default_factory=list)


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
    plan = SearchPlan()
    kb_prefixes: list[str] = []
    conv_ids: set[str] = set()
    memory: list[tuple[str, str | None]] = []
    current_cid = scope.current_conversation_id

    for uri in resolved:
        if isinstance(uri, KbUri):
            if not uri.rel_path and uri.is_dir:
                plan.kb_all = True
            else:
                prefix = uri.rel_path.replace("\\", "/")
                if uri.is_dir:
                    prefix = prefix.rstrip("/") + "/"
                kb_prefixes.append(prefix)
        elif isinstance(uri, ConversationUri):
            ids, names_current = _conversation_ids(scope, uri)
            conv_ids.update(ids)
            if names_current and current_cid and current_cid in ids:
                plan.include_current_conversation = True
        elif isinstance(uri, MemoryUri):
            memory.append(_memory_target(uri))

    if plan.kb_all:
        plan.kb_prefixes = [KB_WHOLE_PREFIX]
    elif kb_prefixes:
        plan.kb_prefixes = list(dict.fromkeys(kb_prefixes))
    else:
        plan.kb_prefixes = None

    if conv_ids:
        plan.conversation_ids = sorted(conv_ids)
    else:
        plan.conversation_ids = None

    plan.memory_targets = _dedupe_memory(memory)
    return plan


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
    """返回会话 id 集合，以及该 URI 是否显式点名某会话（含消息 URI）。"""
    explicit = uri.conversation_id is not None
    if uri.conversation_id:
        return {uri.conversation_id}, explicit
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
        if uri.owner and not uri.conversation_id:
            return set(
                scope.conversations.list_ids_for_channel_instance(uri.owner)
            ), False
    return set(), False


def _memory_target(uri: MemoryUri) -> tuple[str, str | None]:
    kind_filter = uri.kind if uri.kind else None
    if uri.scope_kind == "owner":
        return ("owner", kind_filter)
    if uri.scope_kind == "role":
        assert uri.subject
        return (role_scope(uri.subject), kind_filter)
    assert uri.subject
    return (persona_scope(uri.subject), kind_filter)


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
