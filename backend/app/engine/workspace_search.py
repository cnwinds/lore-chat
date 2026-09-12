"""用户侧工作区搜索：会话 FTS+向量、角色名、知识库 FTS+向量。

检索器本身面向 RAG（向量近邻即可入围）。面板搜索是「人对着关键词找」，
向量只参与排序/召回，展示前必须能在正文里看见查询词，否则会把「1」「3」
这种短消息当近邻塞进来。
"""

from __future__ import annotations

from typing import Any, Iterable

from app.index.search_query import compile_search_query

SEARCH_SCOPES = frozenset({"all", "messages", "roles", "files"})
_SNIPPET_LIMIT = 160


def _list_sidebar_roles(roles) -> list[dict[str, Any]]:
    if not hasattr(roles, "list_all"):
        return []
    try:
        listed = roles.list_all(visibility="sidebar")
    except TypeError:
        listed = roles.list_all()
    return [
        role
        for role in listed
        if (role.get("visibility") or "sidebar") != "hidden"
    ]


def _snippet(text: str, query: str = "", limit: int = _SNIPPET_LIMIT) -> str:
    cleaned = (text or "").strip().replace("\n", " ")
    if not cleaned:
        return ""
    start = 0
    if query.strip():
        compiled = compile_search_query(query)
        hay = cleaned.casefold()
        for term in compiled.match_terms or compiled.signal_terms or (query,):
            idx = hay.find(term.casefold())
            if idx >= 0:
                start = max(0, idx - 20)
                break
    piece = cleaned[start:]
    prefix = "…" if start else ""
    if len(prefix) + len(piece) > limit:
        piece = piece[: limit - len(prefix) - 1] + "…"
    return prefix + piece


def hit_has_query_evidence(text: str, query: str) -> bool:
    """查询词（或其编译项）必须作为子串出现在可见文本里。"""
    compiled = compile_search_query(query)
    hay = (text or "").casefold()
    if not hay:
        return False
    terms = compiled.match_terms or compiled.signal_terms
    if not terms:
        return query.casefold() in hay
    return any(term.casefold() in hay for term in terms)


def _role_matches(role: dict[str, Any], q: str) -> bool:
    compiled = compile_search_query(q)
    hay = f"{role.get('name') or ''} {role.get('system_prompt') or ''}".casefold()
    terms = compiled.match_terms or compiled.signal_terms
    if not terms:
        needle = q.strip().casefold()
        return bool(needle) and needle in hay
    return any(term.casefold() in hay for term in terms)


def match_roles(roles: Iterable[dict[str, Any]], q: str, *, k: int) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for role in roles:
        if not _role_matches(role, q):
            continue
        name = role.get("name") or "角色"
        hits.append(
            {
                "kind": "role",
                "conversation_id": "",
                "message_id": None,
                "role_id": role.get("id") or "",
                "role_name": name,
                "role_avatar": role.get("avatar"),
                "title": name,
                "snippet": _snippet(role.get("system_prompt") or "", q) or "角色",
                "ts": role.get("updated_at"),
            }
        )
        if len(hits) >= k:
            break
    return hits


def _role_meta(conversations: Any, roles: Any, cid: str) -> tuple[str, str, Any]:
    try:
        rid = conversations.get_role_id(cid)
    except KeyError:
        return "", "", None
    try:
        role = roles.get(rid)
    except KeyError:
        return rid, "", None
    return rid, role.get("name") or "", role.get("avatar")


def message_hit_from_retriever(
    hit: Any, *, conversations: Any, roles: Any, query: str = ""
) -> dict[str, Any] | None:
    src = hit.source or ""
    if not src.startswith("conv:"):
        return None
    cid = src[5:]
    rid, rname, ravatar = _role_meta(conversations, roles, cid)
    return {
        "kind": "message",
        "conversation_id": cid,
        "message_id": hit.message_id,
        "role_id": rid,
        "role_name": rname,
        "role_avatar": ravatar,
        "message_role": hit.role,
        "title": hit.conversation_title or "对话",
        "snippet": _snippet(hit.chunk, query),
        "ts": hit.ts,
    }


def file_hit_from_retriever(hit: Any, query: str = "") -> dict[str, Any] | None:
    path = hit.source or ""
    if not path or path.startswith("conv:"):
        return None
    title = path.rsplit("/", 1)[-1]
    return {
        "kind": "file",
        "conversation_id": "",
        "message_id": None,
        "role_id": "",
        "path": path,
        "title": title,
        "snippet": _snippet(hit.chunk, query),
        "ts": None,
    }


def _evidence_blob(mapped: dict[str, Any], raw_text: str) -> str:
    return " ".join(
        part
        for part in (
            raw_text,
            mapped.get("title"),
            mapped.get("role_name"),
            mapped.get("path"),
        )
        if part
    )


def search_workspace(
    *,
    retriever: Any,
    conversations: Any,
    roles: Any,
    q: str,
    k: int = 20,
    scope: str = "messages",
    role_id: str | None = None,
) -> dict[str, Any]:
    query = (q or "").strip()
    kind = scope if scope in SEARCH_SCOPES else "messages"
    limit = max(1, min(int(k or 20), 50))
    if not query:
        return {"hits": [], "tier": "none"}

    hits: list[dict[str, Any]] = []
    tiers: list[str] = []

    if kind in ("all", "roles"):
        hits.extend(match_roles(_list_sidebar_roles(roles), query, k=limit))
        if hits:
            tiers.append("name")

    if kind in ("all", "messages"):
        page = retriever.search(
            query, k=limit, scope="conversations", role_id=role_id
        )
        kept = 0
        for raw in page.hits:
            mapped = message_hit_from_retriever(
                raw, conversations=conversations, roles=roles, query=query
            )
            if mapped is None:
                continue
            if role_id and mapped["role_id"] != role_id:
                continue
            mapped_role = mapped.get("role_id")
            if mapped_role and hasattr(roles, "get"):
                try:
                    if roles.get(mapped_role).get("visibility") == "hidden":
                        continue
                except KeyError:
                    pass
            if not hit_has_query_evidence(_evidence_blob(mapped, raw.chunk), query):
                continue
            hits.append(mapped)
            kept += 1
        if kept:
            tiers.append(getattr(page, "match_strength", "") or "none")

    if kind in ("all", "files"):
        page = retriever.search(query, k=limit, scope="knowledge")
        kept = 0
        for raw in page.hits:
            mapped = file_hit_from_retriever(raw, query=query)
            if mapped is None:
                continue
            if not hit_has_query_evidence(_evidence_blob(mapped, raw.chunk), query):
                continue
            hits.append(mapped)
            kept += 1
        if kept:
            tiers.append(getattr(page, "match_strength", "") or "none")

    if kind != "all" and len(hits) > limit:
        hits = hits[:limit]

    tier = "none"
    for candidate in ("strong", "strict", "name", "relaxed", "like", "weak"):
        if candidate in tiers:
            tier = candidate
            break
    return {"hits": hits, "tier": tier}
