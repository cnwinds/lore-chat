"""lore:// 目录列举（只读视图）。"""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Any

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

LIST_PAGE_SIZE = 200
_SKIP_DIR_NAMES = frozenset({".git", ".kb"})


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
    """单次 walk 目标目录子树，跳过内部目录与 .gitkeep。"""
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


def _kb_child_index(
    files: list[str], dir_path: str
) -> tuple[dict[str, int], dict[str, set[str]], dict[str, set[str]]]:
    """子树内各目录：直接子目录名、直接文件名、该目录下文件总数（含递归）。"""
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
        for depth in range(len(parts)):
            parent = base if depth == 0 else f"{base}/{'/'.join(parts[:depth])}"
            file_counts[parent] = file_counts.get(parent, 0) + 1
        parent = base
        if len(parts) == 1:
            child_files.setdefault(parent, set()).add(parts[0])
        else:
            child_dirs.setdefault(parent, set()).add(parts[0])
    return file_counts, child_dirs, child_files


def _list_kb_at(
    repo: KnowledgeRepo,
    uri: KbUri,
    *,
    depth: int,
    base_depth: int,
    files: list[str] | None = None,
) -> list[dict[str, Any]]:
    dir_path = uri.rel_path.replace("\\", "/").strip("/")
    if files is None:
        files = _walk_kb_rel_files(repo, dir_path)
    file_counts, child_dirs, child_files = _kb_child_index(files, dir_path)
    entries: list[dict[str, Any]] = []

    def append_dir(name: str, rel_depth: int, remaining: int) -> None:
        child_path = f"{dir_path}/{name}".strip("/") if dir_path else name
        entries.append(
            {
                "uri": format_uri(KbUri(child_path, True)),
                "name": name,
                "type": "dir",
                "depth": rel_depth,
                "child_count": file_counts.get(child_path, 0),
            }
        )
        if remaining > 1:
            entries.extend(
                _list_kb_at(
                    repo,
                    KbUri(child_path, True),
                    depth=remaining - 1,
                    base_depth=rel_depth,
                    files=files,
                )
            )

    for name in sorted(child_dirs.get(dir_path, set())):
        append_dir(name, base_depth + 1, depth)
    for name in sorted(child_files.get(dir_path, set())):
        child_path = f"{dir_path}/{name}".strip("/") if dir_path else name
        rel_depth = base_depth + 1
        kind = classify(child_path)
        item: dict[str, Any] = {
            "uri": format_uri(KbUri(child_path, False)),
            "name": name,
            "type": kind,
            "depth": rel_depth,
        }
        abs_p = repo.abs_path(child_path)
        if repo.is_protected(child_path):
            item["protected"] = True
        if kind == "doc":
            title = _kb_doc_title(abs_p)
            if title:
                item["title"] = title
        elif kind in ("text", "binary"):
            try:
                item["size"] = abs_p.stat().st_size
            except OSError:
                item["size"] = 0
            if kind == "binary":
                mime, _ = mimetypes.guess_type(name)
                if mime:
                    item["mime"] = mime
        entries.append(item)
    return entries


def _visible_top_level(scope: ViewScope) -> list[dict[str, Any]]:
    roots = scope.visible_roots()
    has_kb = any(isinstance(r, KbUri) for r in roots)
    has_conv = any(isinstance(r, ConversationUri) for r in roots)
    has_mem = any(isinstance(r, MemoryUri) for r in roots)
    out: list[dict[str, Any]] = []
    if has_kb:
        out.append(
            {"uri": "lore://kb/", "name": "kb", "type": "dir", "depth": 1}
        )
    if has_conv:
        out.append(
            {
                "uri": "lore://conversations/",
                "name": "conversations",
                "type": "dir",
                "depth": 1,
            }
        )
    if has_mem:
        out.append(
            {"uri": "lore://memory/", "name": "memory", "type": "dir", "depth": 1}
        )
    return out


def _conv_entry(
    scope: ViewScope,
    *,
    cid: str,
    bucket: str,
    owner: str | None,
    summary: dict,
    base_depth: int,
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
        "depth": base_depth + 1,
        "title": title,
        "updated_at": summary.get("last_activity") or "",
        "message_count": int(summary.get("message_count") or 0),
    }


def _list_conversations(
    scope: ViewScope,
    uri: ConversationRoot | ConversationUri,
    *,
    depth: int,
    base_depth: int,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    conv = scope.conversations

    if isinstance(uri, ConversationRoot):
        if scope.turn_kind == "channel":
            cid = scope.conversation_id
            inst = scope.channel_instance_id
            if cid and inst:
                rows = conv.list_context_view_summaries([cid])
                if rows:
                    entries.append(
                        _conv_entry(
                            scope,
                            cid=cid,
                            bucket="channels",
                            owner=inst,
                            summary=rows[0],
                            base_depth=base_depth,
                        )
                    )
            return entries
        entries.append(
            {
                "uri": "lore://conversations/dm/",
                "name": "dm",
                "type": "dir",
                "depth": base_depth + 1,
            }
        )
        entries.append(
            {
                "uri": "lore://conversations/rooms/",
                "name": "rooms",
                "type": "dir",
                "depth": base_depth + 1,
            }
        )
        if depth > 1:
            entries.extend(
                _list_conversations(
                    scope,
                    ConversationUri("dm", None, None, None, True),
                    depth=depth - 1,
                    base_depth=base_depth + 1,
                )
            )
        return entries

    if uri.conversation_id:
        return []

    if uri.bucket == "dm" and uri.owner and not uri.is_dir:
        return []

    if uri.bucket == "dm" and not uri.owner:
        for rid in scope.visible_sidebar_role_ids():
            try:
                role = scope.roles.get(rid)
                rname = role.get("name") or rid
            except KeyError:
                rname = rid
            cids = conv.list_owner_dm_conversation_ids_for_role(rid)
            entries.append(
                {
                    "uri": format_uri(ConversationUri("dm", rid, None, None, True)),
                    "name": rname,
                    "type": "dir",
                    "depth": base_depth + 1,
                    "conversation_count": len(cids),
                }
            )
        return entries

    if uri.bucket == "dm" and uri.owner:
        cids = conv.list_owner_dm_conversation_ids_for_role(uri.owner)
        summaries = {
            r["id"]: r for r in conv.list_context_view_summaries(cids)
        }
        rows = [
            _conv_entry(
                scope,
                cid=cid,
                bucket="dm",
                owner=uri.owner,
                summary=summaries.get(cid, {"id": cid}),
                base_depth=base_depth,
            )
            for cid in cids
        ]
        rows.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
        return rows

    if uri.bucket == "rooms":
        cids = conv.list_room_conversation_ids()
        summaries = {
            r["id"]: r for r in conv.list_context_view_summaries(cids)
        }
        rows = [
            _conv_entry(
                scope,
                cid=cid,
                bucket="rooms",
                owner=None,
                summary=summaries.get(cid, {"id": cid}),
                base_depth=base_depth,
            )
            for cid in cids
        ]
        rows.sort(key=lambda x: x.get("updated_at") or "", reverse=True)
        return rows

    return entries


def _memory_kind_counts(store, kinds: frozenset[str]) -> dict[str, int]:
    counts = {k: 0 for k in kinds}
    for f in store.list_confirmed():
        cat = f.get("category") or ""
        if cat in counts:
            counts[cat] += 1
    return counts


def _list_memory_root(scope: ViewScope, *, base_depth: int) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if scope.turn_kind == "owner" or scope.include_owner_memory:
        entries.append(
            {
                "uri": "lore://memory/owner/",
                "name": "owner",
                "type": "dir",
                "depth": base_depth + 1,
            }
        )
    if scope.turn_kind == "owner":
        entries.append(
            {
                "uri": "lore://memory/role/",
                "name": "role",
                "type": "dir",
                "depth": base_depth + 1,
            }
        )
    for pid in scope._visible_persona_ids():
        entries.append(
            {
                "uri": f"lore://memory/persona/{pid}/",
                "name": pid,
                "type": "dir",
                "depth": base_depth + 1,
            }
        )
    return entries


def _list_memory(
    scope: ViewScope,
    uri: MemoryRoot | MemoryUri,
    *,
    depth: int,
    base_depth: int,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    cards = scope.cards

    if isinstance(uri, MemoryRoot):
        return _list_memory_root(scope, base_depth=base_depth)

    if uri.item_id:
        return []

    if uri.scope_kind == "owner" and not uri.kind:
        counts = _memory_kind_counts(cards.owner.store, CATEGORIES)
        for kind in sorted(CATEGORIES):
            entries.append(
                {
                    "uri": f"lore://memory/owner/{kind}/",
                    "name": kind,
                    "type": "dir",
                    "depth": base_depth + 1,
                    "count": counts.get(kind, 0),
                }
            )
        return entries

    if uri.scope_kind == "owner" and uri.kind and not uri.item_id:
        for f in cards.owner.store.list_confirmed():
            if f.get("category") != uri.kind:
                continue
            stmt = (f.get("statement") or "").strip()
            preview = stmt[:80] + ("…" if len(stmt) > 80 else "")
            entries.append(
                {
                    "uri": format_uri(
                        MemoryUri("owner", None, uri.kind, f["id"], False)
                    ),
                    "name": f["id"],
                    "type": uri.kind,
                    "depth": base_depth + 1,
                    "preview": preview,
                }
            )
        return entries

    if uri.scope_kind == "role" and not uri.subject:
        for rid in scope.visible_sidebar_role_ids():
            try:
                role = scope.roles.get(rid)
                rname = role.get("name") or rid
            except KeyError:
                rname = rid
            entries.append(
                {
                    "uri": format_uri(MemoryUri("role", rid, None, None, True)),
                    "name": rname,
                    "type": "dir",
                    "depth": base_depth + 1,
                }
            )
        return entries

    if uri.scope_kind == "role" and uri.subject and not uri.kind:
        store = cards.store(f"role:{uri.subject}")
        counts = _memory_kind_counts(store, frozenset(CARD_KINDS))
        for kind in CARD_KINDS:
            entries.append(
                {
                    "uri": format_uri(
                        MemoryUri("role", uri.subject, kind, None, True)
                    ),
                    "name": kind,
                    "type": "dir",
                    "depth": base_depth + 1,
                    "count": counts.get(kind, 0),
                }
            )
        return entries

    if uri.scope_kind == "role" and uri.subject and uri.kind and not uri.item_id:
        store = cards.store(f"role:{uri.subject}")
        for f in store.list_confirmed():
            if f.get("category") != uri.kind:
                continue
            stmt = (f.get("statement") or "").strip()
            preview = stmt[:80] + ("…" if len(stmt) > 80 else "")
            entries.append(
                {
                    "uri": format_uri(
                        MemoryUri("role", uri.subject, uri.kind, f["id"], False)
                    ),
                    "name": f["id"],
                    "type": uri.kind,
                    "depth": base_depth + 1,
                    "preview": preview,
                }
            )
        return entries

    if uri.scope_kind == "persona" and not uri.subject:
        for pid in scope._visible_persona_ids():
            entries.append(
                {
                    "uri": format_uri(MemoryUri("persona", pid, None, None, True)),
                    "name": pid,
                    "type": "dir",
                    "depth": base_depth + 1,
                }
            )
        return entries

    if uri.scope_kind == "persona" and uri.subject and not uri.kind:
        store = cards.store(f"persona:{uri.subject}")
        counts = _memory_kind_counts(store, frozenset(CARD_KINDS))
        for kind in CARD_KINDS:
            entries.append(
                {
                    "uri": format_uri(
                        MemoryUri("persona", uri.subject, kind, None, True)
                    ),
                    "name": kind,
                    "type": "dir",
                    "depth": base_depth + 1,
                    "count": counts.get(kind, 0),
                }
            )
        return entries

    if uri.scope_kind == "persona" and uri.subject and uri.kind and not uri.item_id:
        store = cards.store(f"persona:{uri.subject}")
        for f in store.list_confirmed():
            if f.get("category") != uri.kind:
                continue
            stmt = (f.get("statement") or "").strip()
            preview = stmt[:80] + ("…" if len(stmt) > 80 else "")
            entries.append(
                {
                    "uri": format_uri(
                        MemoryUri("persona", uri.subject, uri.kind, f["id"], False)
                    ),
                    "name": f["id"],
                    "type": uri.kind,
                    "depth": base_depth + 1,
                    "preview": preview,
                }
            )
        return entries

    return entries


def list_entries(
    scope: ViewScope,
    repo: KnowledgeRepo,
    parsed: LoreUri,
    *,
    depth: int,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], bool, int]:
    depth = max(1, min(3, int(depth)))
    if isinstance(parsed, LoreRoot):
        flat = _visible_top_level(scope)
    elif isinstance(parsed, KbUri):
        if not parsed.is_dir:
            return [], False, offset
        dir_path = parsed.rel_path.replace("\\", "/").strip("/")
        kb_files = _walk_kb_rel_files(repo, dir_path)
        flat = _list_kb_at(
            repo, parsed, depth=depth, base_depth=0, files=kb_files
        )
    elif isinstance(parsed, (ConversationRoot, ConversationUri)):
        if isinstance(parsed, ConversationUri) and parsed.conversation_id:
            return [], False, offset
        flat = _list_conversations(scope, parsed, depth=depth, base_depth=0)
    elif isinstance(parsed, (MemoryRoot, MemoryUri)):
        flat = _list_memory(scope, parsed, depth=depth, base_depth=0)
    else:
        flat = []

    page = flat[offset : offset + LIST_PAGE_SIZE]
    has_more = offset + LIST_PAGE_SIZE < len(flat)
    next_offset = offset + len(page)
    return page, has_more, next_offset
