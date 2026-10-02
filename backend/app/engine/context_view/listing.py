"""lore:// 目录列举（只读视图）。"""

from __future__ import annotations

import fnmatch
import mimetypes
import os
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.engine.context_view.errors import NotFound
from app.engine.context_view.kb_kind import classify
from app.engine.context_view.scope import ViewScope
from app.engine.context_view.uri import (
    ConversationRoot,
    ConversationUri,
    KbUri,
    LoreRoot,
    LoreUri,
    MemoryRoot,
    MemoryUri,
    format_uri,
    is_kb_internal,
)
from app.engine.memory.cards import CARD_KINDS
from app.engine.memory.constants import CATEGORIES
from app.engine.secrets import mask_secrets
from app.storage.frontmatter import parse as parse_frontmatter
from app.storage.repo import KnowledgeRepo
from app.time import ts_in_search_range

LIST_PAGE_SIZE = 200
LIST_MAX_DEPTH = 5
FILES_PER_DIR_CAP = 20
_SKIP_DIR_NAMES = frozenset({".git", ".kb"})

EntryTypeFilter = Literal["dir", "doc", "text", "binary", "conversation", "memory"]


@dataclass
class ListNode:
    entry: dict[str, Any]
    children: list[ListNode] = field(default_factory=list)


@dataclass
class ListResult:
    entries: list[dict[str, Any]]
    has_more: bool
    next_offset: int
    unexpanded_dirs: int = 0
    omitted_files: int = 0
    unlisted: int = 0


def parse_list_depth(raw: object, *, has_filter: bool) -> int:
    if has_filter and raw is None:
        return LIST_MAX_DEPTH
    default = 1
    if raw is None or raw is True or raw is False:
        return default
    if isinstance(raw, bool):
        return default
    if isinstance(raw, int):
        d = raw
    elif isinstance(raw, str):
        s = raw.strip()
        if not s:
            return default
        try:
            d = int(s)
        except ValueError:
            return default
    else:
        return default
    return max(1, min(LIST_MAX_DEPTH, d))


def _type_matches(type_filter: str | None, entry: dict[str, Any]) -> bool:
    if not type_filter or not str(type_filter).strip():
        return True
    tf = str(type_filter).strip().lower()
    et = str(entry.get("type") or "").lower()
    if tf == "memory":
        return et not in ("dir", "doc", "text", "binary", "conversation")
    return et == tf


def _ts_matches(
    entry: dict[str, Any],
    ts_after: str | None,
    ts_before: str | None,
) -> bool:
    if not ts_after and not ts_before:
        return True
    if entry.get("type") != "conversation":
        return False
    ts = entry.get("updated_at") or ""
    return ts_in_search_range(ts, ts_after, ts_before)


def _name_pattern_matches(pat: str, name: str) -> bool:
    if "*" not in pat and "?" not in pat and "[" not in pat:
        return pat.casefold() in name.casefold()
    return fnmatch.fnmatch(name.casefold(), pat.casefold())


def _kb_doc_title(abs_path: Path) -> str | None:
    try:
        with abs_path.open("rb") as fh:
            head = fh.read(8192)
        meta, _ = parse_frontmatter(head.decode("utf-8", errors="replace"))
        title = (meta.get("title") or "").strip()
        return title or None
    except OSError:
        return None


def _walk_kb_rel_files(repo: KnowledgeRepo, dir_path: str) -> list[str]:
    base = repo.root if not dir_path else repo.root / dir_path
    if not base.is_dir():
        return []
    out: list[str] = []
    prefix = f"{dir_path}/" if dir_path else ""
    for dirpath, dirnames, filenames in os.walk(base, topdown=True):
        dirnames[:] = [
            d for d in dirnames if d not in _SKIP_DIR_NAMES and not d.startswith(".")
        ]
        for name in filenames:
            if name == ".gitkeep":
                continue
            abs_p = Path(dirpath) / name
            rel = abs_p.relative_to(repo.root).as_posix()
            if is_kb_internal(rel):
                continue
            if dir_path and not rel.startswith(prefix):
                continue
            out.append(rel)
    return sorted(out)


def _kb_index_key(base: str, parts: list[str], *, end: int) -> str:
    """知识库索引用的目录键（无 leading slash，空 base 与空段跳过）。"""
    segs = [p for p in ([base] if base else []) + parts[:end] if p]
    return "/".join(segs)


def _kb_child_index(
    files: list[str], dir_path: str
) -> tuple[dict[str, int], dict[str, set[str]], dict[str, set[str]]]:
    child_dirs: dict[str, set[str]] = {}
    child_files: dict[str, set[str]] = {}
    file_counts: dict[str, int] = {}
    base = dir_path
    for rel in files:
        if base:
            if not rel.startswith(base + "/"):
                continue
            rest = rel[len(base) + 1 :]
        else:
            rest = rel
        if not rest:
            continue
        parts = rest.split("/")
        for depth_i in range(len(parts)):
            parent = _kb_index_key(base, parts, end=depth_i)
            file_counts[parent] = file_counts.get(parent, 0) + 1
        for depth_i, part in enumerate(parts):
            parent = _kb_index_key(base, parts, end=depth_i)
            if depth_i == len(parts) - 1:
                child_files.setdefault(parent, set()).add(part)
            else:
                child_dirs.setdefault(parent, set()).add(part)
    return file_counts, child_dirs, child_files


def _kb_stub_dir(child_path: str, name: str, depth: int, child_count: int) -> dict[str, Any]:
    return {
        "uri": format_uri(KbUri(child_path, True)),
        "name": name,
        "type": "dir",
        "depth": depth,
        "child_count": child_count,
    }


def _kb_stub_file(child_path: str, depth: int) -> dict[str, Any]:
    name = child_path.rsplit("/", 1)[-1]
    return {
        "uri": format_uri(KbUri(child_path, False)),
        "name": name,
        "type": classify(child_path),
        "depth": depth,
    }


def _build_kb_children(
    dir_path: str,
    *,
    base_depth: int,
    remaining: int,
    file_counts: dict[str, int],
    child_dirs: dict[str, set[str]],
    child_files: dict[str, set[str]],
) -> list[ListNode]:
    if remaining <= 0:
        return []
    nodes: list[ListNode] = []
    for name in sorted(child_dirs.get(dir_path, set())):
        child_path = f"{dir_path}/{name}".strip("/") if dir_path else name
        entry = _kb_stub_dir(
            child_path, name, base_depth + 1, file_counts.get(child_path, 0)
        )
        sub = _build_kb_children(
            child_path,
            base_depth=base_depth + 1,
            remaining=remaining - 1,
            file_counts=file_counts,
            child_dirs=child_dirs,
            child_files=child_files,
        )
        nodes.append(ListNode(entry=entry, children=sub))
    for name in sorted(child_files.get(dir_path, set())):
        child_path = f"{dir_path}/{name}".strip("/") if dir_path else name
        nodes.append(
            ListNode(entry=_kb_stub_file(child_path, base_depth + 1), children=[])
        )
    return nodes


def _conv_stub(
    *,
    cid: str,
    bucket: str,
    owner: str | None,
    summary: dict,
    depth: int,
) -> dict[str, Any]:
    cu = ConversationUri(
        bucket=bucket,  # type: ignore[arg-type]
        owner=owner,
        conversation_id=cid,
        message_id=None,
        is_dir=True,
    )
    raw_title = (summary.get("title") or "").strip()
    title, _ = mask_secrets(raw_title or cid)
    return {
        "uri": format_uri(cu),
        "name": cid,
        "type": "conversation",
        "depth": depth,
        "title": title,
        "updated_at": summary.get("last_activity") or "",
        "message_count": int(summary.get("message_count") or 0),
    }


def _build_conversation_children(
    scope: ViewScope,
    parsed: ConversationRoot | ConversationUri,
    *,
    base_depth: int,
    remaining: int,
    ts_after: str | None,
    ts_before: str | None,
) -> list[ListNode]:
    if remaining <= 0:
        return []
    conv = scope.conversations
    nodes: list[ListNode] = []

    if isinstance(parsed, ConversationRoot):
        if scope.turn_kind == "channel":
            cid = scope.conversation_id
            inst = scope.channel_instance_id
            if cid and inst:
                rows = conv.list_context_view_summaries([cid])
                if rows:
                    ent = _conv_stub(
                        cid=cid,
                        bucket="channels",
                        owner=inst,
                        summary=rows[0],
                        depth=base_depth + 1,
                    )
                    if _ts_matches(ent, ts_after, ts_before):
                        nodes.append(ListNode(entry=ent, children=[]))
            return nodes
        dm = ListNode(
            entry={
                "uri": "lore://conversations/dm/",
                "name": "dm",
                "type": "dir",
                "depth": base_depth + 1,
            },
            children=_build_conversation_children(
                scope,
                ConversationUri("dm", None, None, None, True),
                base_depth=base_depth + 1,
                remaining=remaining - 1,
                ts_after=ts_after,
                ts_before=ts_before,
            )
            if remaining > 1
            else [],
        )
        rooms = ListNode(
            entry={
                "uri": "lore://conversations/rooms/",
                "name": "rooms",
                "type": "dir",
                "depth": base_depth + 1,
            },
            children=_build_conversation_children(
                scope,
                ConversationUri("rooms", None, None, None, True),
                base_depth=base_depth + 1,
                remaining=remaining - 1,
                ts_after=ts_after,
                ts_before=ts_before,
            )
            if remaining > 1
            else [],
        )
        return [dm, rooms]

    if isinstance(parsed, ConversationUri) and parsed.conversation_id:
        return []

    if parsed.bucket == "dm" and not parsed.owner:
        for rid in scope.visible_sidebar_role_ids():
            try:
                role = scope.roles.get(rid)
                rname = role.get("name") or rid
            except KeyError:
                rname = rid
            cids = conv.list_owner_dm_conversation_ids_for_role(rid)
            entry = {
                "uri": format_uri(ConversationUri("dm", rid, None, None, True)),
                "name": rname,
                "type": "dir",
                "depth": base_depth + 1,
                "conversation_count": len(cids),
            }
            sub = (
                _build_conversation_children(
                    scope,
                    ConversationUri("dm", rid, None, None, True),
                    base_depth=base_depth + 1,
                    remaining=remaining - 1,
                    ts_after=ts_after,
                    ts_before=ts_before,
                )
                if remaining > 1
                else []
            )
            nodes.append(ListNode(entry=entry, children=sub))
        return nodes

    if parsed.bucket == "dm" and parsed.owner:
        cids = conv.list_owner_dm_conversation_ids_for_role(parsed.owner)
        summaries = {r["id"]: r for r in conv.list_context_view_summaries(cids)}
        rows = []
        for cid in cids:
            ent = _conv_stub(
                cid=cid,
                bucket="dm",
                owner=parsed.owner,
                summary=summaries.get(cid, {"id": cid}),
                depth=base_depth + 1,
            )
            if _ts_matches(ent, ts_after, ts_before):
                rows.append(ListNode(entry=ent, children=[]))
        rows.sort(key=lambda n: n.entry.get("updated_at") or "", reverse=True)
        return rows

    if parsed.bucket == "rooms":
        cids = conv.list_room_conversation_ids()
        summaries = {r["id"]: r for r in conv.list_context_view_summaries(cids)}
        rows = []
        for cid in cids:
            ent = _conv_stub(
                cid=cid,
                bucket="rooms",
                owner=None,
                summary=summaries.get(cid, {"id": cid}),
                depth=base_depth + 1,
            )
            if _ts_matches(ent, ts_after, ts_before):
                rows.append(ListNode(entry=ent, children=[]))
        rows.sort(key=lambda n: n.entry.get("updated_at") or "", reverse=True)
        return rows

    return nodes


def _memory_kind_counts(store, kinds: frozenset[str]) -> dict[str, int]:
    counts = {k: 0 for k in kinds}
    for f in store.list_confirmed():
        cat = f.get("category") or ""
        if cat in counts:
            counts[cat] += 1
    return counts


def _build_memory_children(
    scope: ViewScope,
    parsed: MemoryRoot | MemoryUri,
    *,
    base_depth: int,
    remaining: int,
) -> list[ListNode]:
    if remaining <= 0:
        return []
    cards = scope.cards
    nodes: list[ListNode] = []

    if isinstance(parsed, MemoryRoot):
        if scope.turn_kind == "owner" or scope.include_owner_memory:
            nodes.append(
                ListNode(
                    entry={
                        "uri": "lore://memory/owner/",
                        "name": "owner",
                        "type": "dir",
                        "depth": base_depth + 1,
                    },
                    children=_build_memory_children(
                        scope,
                        MemoryUri("owner", None, None, None, True),
                        base_depth=base_depth + 1,
                        remaining=remaining - 1,
                    )
                    if remaining > 1
                    else [],
                )
            )
        if scope.turn_kind == "owner":
            nodes.append(
                ListNode(
                    entry={
                        "uri": "lore://memory/role/",
                        "name": "role",
                        "type": "dir",
                        "depth": base_depth + 1,
                    },
                    children=_build_memory_children(
                        scope,
                        MemoryUri("role", None, None, None, True),
                        base_depth=base_depth + 1,
                        remaining=remaining - 1,
                    )
                    if remaining > 1
                    else [],
                )
            )
        for pid in scope._visible_persona_ids():
            nodes.append(
                ListNode(
                    entry={
                        "uri": f"lore://memory/persona/{pid}/",
                        "name": pid,
                        "type": "dir",
                        "depth": base_depth + 1,
                    },
                    children=_build_memory_children(
                        scope,
                        MemoryUri("persona", pid, None, None, True),
                        base_depth=base_depth + 1,
                        remaining=remaining - 1,
                    )
                    if remaining > 1
                    else [],
                )
            )
        return nodes

    if parsed.item_id:
        return []

    if parsed.scope_kind == "owner" and not parsed.kind:
        counts = _memory_kind_counts(cards.owner.store, CATEGORIES)
        for kind in sorted(CATEGORIES):
            entry = {
                "uri": f"lore://memory/owner/{kind}/",
                "name": kind,
                "type": "dir",
                "depth": base_depth + 1,
                "count": counts.get(kind, 0),
            }
            sub = (
                _build_memory_children(
                    scope,
                    MemoryUri("owner", None, kind, None, True),
                    base_depth=base_depth + 1,
                    remaining=remaining - 1,
                )
                if remaining > 1
                else []
            )
            nodes.append(ListNode(entry=entry, children=sub))
        return nodes

    if parsed.scope_kind == "owner" and parsed.kind and not parsed.item_id:
        for f in cards.owner.store.list_confirmed():
            if f.get("category") != parsed.kind:
                continue
            stmt = (f.get("statement") or "").strip()
            preview = stmt[:80] + ("…" if len(stmt) > 80 else "")
            nodes.append(
                ListNode(
                    entry={
                        "uri": format_uri(
                            MemoryUri("owner", None, parsed.kind, f["id"], False)
                        ),
                        "name": f["id"],
                        "type": parsed.kind,
                        "depth": base_depth + 1,
                        "preview": preview,
                    },
                    children=[],
                )
            )
        return nodes

    if parsed.scope_kind == "role" and not parsed.subject:
        for rid in scope.visible_sidebar_role_ids():
            try:
                role = scope.roles.get(rid)
                rname = role.get("name") or rid
            except KeyError:
                rname = rid
            entry = {
                "uri": format_uri(MemoryUri("role", rid, None, None, True)),
                "name": rname,
                "type": "dir",
                "depth": base_depth + 1,
            }
            sub = (
                _build_memory_children(
                    scope,
                    MemoryUri("role", rid, None, None, True),
                    base_depth=base_depth + 1,
                    remaining=remaining - 1,
                )
                if remaining > 1
                else []
            )
            nodes.append(ListNode(entry=entry, children=sub))
        return nodes

    if parsed.scope_kind == "role" and parsed.subject and not parsed.kind:
        store = cards.store(f"role:{parsed.subject}")
        counts = _memory_kind_counts(store, frozenset(CARD_KINDS))
        for kind in CARD_KINDS:
            entry = {
                "uri": format_uri(
                    MemoryUri("role", parsed.subject, kind, None, True)
                ),
                "name": kind,
                "type": "dir",
                "depth": base_depth + 1,
                "count": counts.get(kind, 0),
            }
            sub = (
                _build_memory_children(
                    scope,
                    MemoryUri("role", parsed.subject, kind, None, True),
                    base_depth=base_depth + 1,
                    remaining=remaining - 1,
                )
                if remaining > 1
                else []
            )
            nodes.append(ListNode(entry=entry, children=sub))
        return nodes

    if parsed.scope_kind == "role" and parsed.subject and parsed.kind and not parsed.item_id:
        store = cards.store(f"role:{parsed.subject}")
        for f in store.list_confirmed():
            if f.get("category") != parsed.kind:
                continue
            stmt = (f.get("statement") or "").strip()
            preview = stmt[:80] + ("…" if len(stmt) > 80 else "")
            nodes.append(
                ListNode(
                    entry={
                        "uri": format_uri(
                            MemoryUri("role", parsed.subject, parsed.kind, f["id"], False)
                        ),
                        "name": f["id"],
                        "type": parsed.kind,
                        "depth": base_depth + 1,
                        "preview": preview,
                    },
                    children=[],
                )
            )
        return nodes

    if parsed.scope_kind == "persona" and not parsed.subject:
        for pid in scope._visible_persona_ids():
            entry = {
                "uri": format_uri(MemoryUri("persona", pid, None, None, True)),
                "name": pid,
                "type": "dir",
                "depth": base_depth + 1,
            }
            sub = (
                _build_memory_children(
                    scope,
                    MemoryUri("persona", pid, None, None, True),
                    base_depth=base_depth + 1,
                    remaining=remaining - 1,
                )
                if remaining > 1
                else []
            )
            nodes.append(ListNode(entry=entry, children=sub))
        return nodes

    if parsed.scope_kind == "persona" and parsed.subject and not parsed.kind:
        store = cards.store(f"persona:{parsed.subject}")
        counts = _memory_kind_counts(store, frozenset(CARD_KINDS))
        for kind in CARD_KINDS:
            entry = {
                "uri": format_uri(
                    MemoryUri("persona", parsed.subject, kind, None, True)
                ),
                "name": kind,
                "type": "dir",
                "depth": base_depth + 1,
                "count": counts.get(kind, 0),
            }
            sub = (
                _build_memory_children(
                    scope,
                    MemoryUri("persona", parsed.subject, kind, None, True),
                    base_depth=base_depth + 1,
                    remaining=remaining - 1,
                )
                if remaining > 1
                else []
            )
            nodes.append(ListNode(entry=entry, children=sub))
        return nodes

    if parsed.scope_kind == "persona" and parsed.subject and parsed.kind and not parsed.item_id:
        store = cards.store(f"persona:{parsed.subject}")
        for f in store.list_confirmed():
            if f.get("category") != parsed.kind:
                continue
            stmt = (f.get("statement") or "").strip()
            preview = stmt[:80] + ("…" if len(stmt) > 80 else "")
            nodes.append(
                ListNode(
                    entry={
                        "uri": format_uri(
                            MemoryUri(
                                "persona", parsed.subject, parsed.kind, f["id"], False
                            )
                        ),
                        "name": f["id"],
                        "type": parsed.kind,
                        "depth": base_depth + 1,
                        "preview": preview,
                    },
                    children=[],
                )
            )
        return nodes

    return nodes


def _build_lore_root_children(
    scope: ViewScope,
    repo: KnowledgeRepo,
    *,
    base_depth: int,
    remaining: int,
    ts_after: str | None,
    ts_before: str | None,
    kb_index: tuple | None,
) -> list[ListNode]:
    roots = scope.visible_roots()
    has_kb = any(isinstance(r, KbUri) for r in roots)
    has_conv = any(isinstance(r, ConversationUri) for r in roots)
    has_mem = any(isinstance(r, MemoryUri) for r in roots)
    nodes: list[ListNode] = []
    d = base_depth + 1
    sub_rem = remaining - 1
    if has_kb:
        kb_children: list[ListNode] = []
        if remaining > 1 and kb_index is not None:
            fc, cd, cf = kb_index
            kb_children = _build_kb_children(
                "",
                base_depth=d,
                remaining=sub_rem,
                file_counts=fc,
                child_dirs=cd,
                child_files=cf,
            )
        nodes.append(
            ListNode(
                entry={"uri": "lore://kb/", "name": "kb", "type": "dir", "depth": d},
                children=kb_children,
            )
        )
    if has_conv:
        nodes.append(
            ListNode(
                entry={
                    "uri": "lore://conversations/",
                    "name": "conversations",
                    "type": "dir",
                    "depth": d,
                },
                children=_build_conversation_children(
                    scope,
                    ConversationRoot(),
                    base_depth=d,
                    remaining=sub_rem,
                    ts_after=ts_after,
                    ts_before=ts_before,
                )
                if remaining > 1
                else [],
            )
        )
    if has_mem:
        nodes.append(
            ListNode(
                entry={
                    "uri": "lore://memory/",
                    "name": "memory",
                    "type": "dir",
                    "depth": d,
                },
                children=_build_memory_children(
                    scope,
                    MemoryRoot(),
                    base_depth=d,
                    remaining=sub_rem,
                )
                if remaining > 1
                else [],
            )
        )
    return nodes


def build_children_tree(
    scope: ViewScope,
    repo: KnowledgeRepo,
    parsed: LoreUri,
    *,
    depth: int,
    ts_after: str | None = None,
    ts_before: str | None = None,
) -> list[ListNode]:
    """起点目录的直接子节点树（深度不超过 depth）。"""
    kb_index: tuple | None = None
    if isinstance(parsed, KbUri) and parsed.is_dir:
        dir_path = parsed.rel_path.replace("\\", "/").strip("/")
        files = _walk_kb_rel_files(repo, dir_path)
        kb_index = _kb_child_index(files, dir_path)
    elif isinstance(parsed, LoreRoot) and depth > 1:
        files = _walk_kb_rel_files(repo, "")
        kb_index = _kb_child_index(files, "")

    if isinstance(parsed, LoreRoot):
        return _build_lore_root_children(
            scope,
            repo,
            base_depth=0,
            remaining=depth,
            ts_after=ts_after,
            ts_before=ts_before,
            kb_index=kb_index,
        )

    if isinstance(parsed, KbUri):
        if not parsed.is_dir:
            return []
        dir_path = parsed.rel_path.replace("\\", "/").strip("/")
        fc, cd, cf = kb_index  # type: ignore[misc]
        return _build_kb_children(
            dir_path,
            base_depth=0,
            remaining=depth,
            file_counts=fc,
            child_dirs=cd,
            child_files=cf,
        )

    if isinstance(parsed, (ConversationRoot, ConversationUri)):
        if isinstance(parsed, ConversationUri) and parsed.conversation_id:
            return []
        return _build_conversation_children(
            scope,
            parsed,
            base_depth=0,
            remaining=depth,
            ts_after=ts_after,
            ts_before=ts_before,
        )

    if isinstance(parsed, (MemoryRoot, MemoryUri)):
        return _build_memory_children(
            scope, parsed, base_depth=0, remaining=depth
        )

    return []


def enrich_kb_entries(repo: KnowledgeRepo, entries: list[dict[str, Any]]) -> None:
    for ent in entries:
        t = ent.get("type")
        if t not in ("doc", "text", "binary"):
            continue
        uri = ent.get("uri") or ""
        if not uri.startswith("lore://kb/"):
            continue
        path = uri.replace("lore://kb/", "").rstrip("/")
        abs_p = repo.abs_path(path)
        if repo.is_protected(path):
            ent["protected"] = True
        if t == "doc":
            title = _kb_doc_title(abs_p)
            if title:
                ent["title"] = title
        elif t in ("text", "binary"):
            try:
                ent["size"] = abs_p.stat().st_size
            except OSError:
                ent["size"] = 0
            if t == "binary":
                mime, _ = mimetypes.guess_type(ent.get("name") or path)
                if mime:
                    ent["mime"] = mime


def _node_matches_filter(
    repo: KnowledgeRepo,
    node: ListNode,
    *,
    pattern: str | None,
    type_filter: str | None,
    ts_after: str | None,
    ts_before: str | None,
) -> bool:
    ent = node.entry
    if not _type_matches(type_filter, ent):
        return False
    if not _ts_matches(ent, ts_after, ts_before):
        return False
    if not pattern or not str(pattern).strip():
        return True
    pat = str(pattern).strip()
    name = ent.get("name") or ""
    if _name_pattern_matches(pat, name):
        return True
    if ent.get("type") == "doc":
        uri = ent.get("uri") or ""
        path = uri.replace("lore://kb/", "").rstrip("/")
        title = _kb_doc_title(repo.abs_path(path))
        if title and _name_pattern_matches(pat, title):
            ent["title"] = title
            return True
    title = ent.get("title")
    if title and _name_pattern_matches(pat, str(title)):
        return True
    return False


def _preorder_filter_nodes(
    repo: KnowledgeRepo,
    nodes: list[ListNode],
    *,
    pattern: str | None,
    type_filter: str | None,
    ts_after: str | None,
    ts_before: str | None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def walk(ns: list[ListNode]) -> None:
        for n in ns:
            if _node_matches_filter(
                repo,
                n,
                pattern=pattern,
                type_filter=type_filter,
                ts_after=ts_after,
                ts_before=ts_before,
            ):
                out.append(dict(n.entry))
            walk(n.children)

    walk(nodes)
    return out


@dataclass
class _DirExpandState:
    expanded: bool
    omitted_files: int = 0


def _bfs_multilevel(
    children: list[ListNode], *, max_depth: int
) -> tuple[list[dict[str, Any]], ListResult]:
    meta = ListResult(entries=[], has_more=False, next_offset=0)
    if max_depth <= 1:
        flat = [dict(n.entry) for n in children]
        return flat[:LIST_PAGE_SIZE], meta

    included: set[int] = set()
    dir_state: dict[int, _DirExpandState] = {}
    budget = LIST_PAGE_SIZE

    queue: deque[tuple[ListNode, int]] = deque()

    layer_dirs = [n for n in children if n.entry.get("type") == "dir"]
    layer_files = [n for n in children if n.entry.get("type") != "dir"]
    layer_file_cap = layer_files[:FILES_PER_DIR_CAP]
    meta.unlisted = max(0, len(layer_files) - FILES_PER_DIR_CAP)

    for node in layer_dirs + layer_file_cap:
        if budget <= 0:
            meta.unlisted += 1
            continue
        included.add(id(node))
        budget -= 1
        if node.entry.get("type") == "dir" and max_depth > 1:
            queue.append((node, 1))

    while queue:
        node, rel_depth = queue.popleft()
        nid = id(node)
        if nid not in included:
            continue
        if rel_depth >= max_depth:
            dir_state[nid] = _DirExpandState(expanded=False)
            continue

        subdirs = [c for c in node.children if c.entry.get("type") == "dir"]
        files = [c for c in node.children if c.entry.get("type") != "dir"]
        n_files = min(len(files), FILES_PER_DIR_CAP)
        omitted = max(0, len(files) - FILES_PER_DIR_CAP)
        need = len(subdirs) + n_files

        if budget < need:
            dir_state[nid] = _DirExpandState(expanded=False)
            meta.unexpanded_dirs += 1
            continue

        dir_state[nid] = _DirExpandState(expanded=True, omitted_files=omitted)
        meta.omitted_files += omitted

        for sd in subdirs:
            included.add(id(sd))
            budget -= 1
            queue.append((sd, rel_depth + 1))
        for f in files[:FILES_PER_DIR_CAP]:
            included.add(id(f))
            budget -= 1

    def preorder(ns: list[ListNode]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for n in ns:
            if id(n) not in included:
                continue
            ent = dict(n.entry)
            if n.entry.get("type") == "dir":
                st = dir_state.get(id(n))
                if st:
                    ent["expanded"] = st.expanded
                    if st.omitted_files:
                        ent["omitted_files"] = st.omitted_files
            out.append(ent)
            st = dir_state.get(id(n))
            if st and st.expanded:
                out.extend(preorder(n.children))
        return out

    entries = preorder(children)
    meta.entries = entries
    return entries, meta


def single_item_entry(
    scope: ViewScope,
    repo: KnowledgeRepo,
    parsed: LoreUri,
) -> dict[str, Any] | None:
    if isinstance(parsed, KbUri) and not parsed.is_dir and parsed.rel_path:
        path = parsed.rel_path.replace("\\", "/").strip("/")
        uri = format_uri(parsed)
        if not repo.abs_path(path).is_file():
            kind = classify(path)
            if kind == "doc":
                raise NotFound(f"文档不存在：{path}", uri=uri)
            raise NotFound(f"文件不存在：{path}", uri=uri)
        ent = _kb_stub_file(path, 1)
        enrich_kb_entries(repo, [ent])
        return ent
    if isinstance(parsed, ConversationUri) and parsed.conversation_id:
        conv = scope.conversations
        cid = parsed.conversation_id
        bucket, owner = scope.conversation_bucket(cid)
        rows = conv.list_context_view_summaries([cid])
        if not rows:
            raise NotFound(f"未知会话: {cid}", uri=format_uri(parsed))
        return _conv_stub(
            cid=cid,
            bucket=bucket,
            owner=owner,
            summary=rows[0],
            depth=1,
        )
    if isinstance(parsed, MemoryUri) and parsed.item_id and parsed.kind:
        uri = format_uri(parsed)
        cards = scope.cards
        if parsed.scope_kind == "owner":
            fact = cards.owner.store.get_fact(parsed.item_id)
            if (
                not fact
                or fact.get("status") != "confirmed"
                or fact.get("category") != parsed.kind
            ):
                raise NotFound("记忆不存在或未确认", uri=uri)
            stmt = (fact.get("statement") or "").strip()
        else:
            sk = f"{parsed.scope_kind}:{parsed.subject}"
            fact = cards.store(sk).get_fact(parsed.item_id)
            if (
                not fact
                or fact.get("status") != "confirmed"
                or fact.get("category") != parsed.kind
            ):
                raise NotFound("卡片不存在或未确认", uri=uri)
            stmt = (fact.get("statement") or "").strip()
        preview = stmt[:80] + ("…" if len(stmt) > 80 else "")
        return {
            "uri": uri,
            "name": parsed.item_id,
            "type": parsed.kind,
            "depth": 1,
            "preview": preview,
        }
    return None


def list_entries(
    scope: ViewScope,
    repo: KnowledgeRepo,
    parsed: LoreUri,
    *,
    depth: int,
    offset: int = 0,
    pattern: str | None = None,
    type_filter: str | None = None,
    ts_after: str | None = None,
    ts_before: str | None = None,
) -> ListResult:
    single = single_item_entry(scope, repo, parsed)
    if single is not None:
        return ListResult(entries=[single], has_more=False, next_offset=0)

    has_filter = bool(
        (pattern and str(pattern).strip())
        or (type_filter and str(type_filter).strip())
        or ts_after
        or ts_before
    )

    children = build_children_tree(
        scope,
        repo,
        parsed,
        depth=depth,
        ts_after=ts_after,
        ts_before=ts_before,
    )

    if has_filter:
        flat = _preorder_filter_nodes(
            repo,
            children,
            pattern=pattern,
            type_filter=type_filter,
            ts_after=ts_after,
            ts_before=ts_before,
        )
        page = flat[offset : offset + LIST_PAGE_SIZE]
        enrich_kb_entries(repo, page)
        has_more = offset + LIST_PAGE_SIZE < len(flat)
        return ListResult(
            entries=page,
            has_more=has_more,
            next_offset=offset + len(page),
        )

    if depth == 1:
        flat = [dict(n.entry) for n in children]
        page = flat[offset : offset + LIST_PAGE_SIZE]
        enrich_kb_entries(repo, page)
        has_more = offset + LIST_PAGE_SIZE < len(flat)
        return ListResult(
            entries=page,
            has_more=has_more,
            next_offset=offset + len(page),
        )

    entries, meta = _bfs_multilevel(children, max_depth=depth)
    enrich_kb_entries(repo, entries)
    meta.entries = entries
    return meta
