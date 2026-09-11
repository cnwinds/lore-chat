"""用户侧工作区搜索：会话 FTS+向量、角色名、知识库 FTS+向量。"""

from __future__ import annotations

from typing import Any, Iterable

SEARCH_SCOPES = frozenset({"all", "messages", "roles", "files"})
_SNIPPET_LIMIT = 160


def _snippet(text: str, limit: int = _SNIPPET_LIMIT) -> str:
    cleaned = (text or "").strip().replace("\n", " ")
    if len(cleaned) > limit:
        return cleaned[: limit - 1] + "…"
    return cleaned


def _role_matches(role: dict[str, Any], q: str) -> bool:
    needle = q.strip().lower()
    if not needle:
        return True
    name = (role.get("name") or "").lower()
    prompt = (role.get("system_prompt") or "").lower()
    return needle in name or needle in prompt


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
                "snippet": _snippet(role.get("system_prompt") or "") or "角色",
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
    hit: Any, *, conversations: Any, roles: Any
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
        "snippet": _snippet(hit.chunk),
        "ts": hit.ts,
    }


def file_hit_from_retriever(hit: Any) -> dict[str, Any] | None:
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
        "snippet": _snippet(hit.chunk),
        "ts": None,
    }


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
        hits.extend(match_roles(roles.list_all(), query, k=limit))
        if hits:
            tiers.append("name")

    if kind in ("all", "messages"):
        page = retriever.search(
            query, k=limit, scope="conversations", role_id=role_id
        )
        tiers.append(getattr(page, "match_strength", "") or "none")
        for raw in page.hits:
            mapped = message_hit_from_retriever(
                raw, conversations=conversations, roles=roles
            )
            if mapped is None:
                continue
            if role_id and mapped["role_id"] != role_id:
                continue
            hits.append(mapped)

    if kind in ("all", "files"):
        page = retriever.search(query, k=limit, scope="knowledge")
        tiers.append(getattr(page, "match_strength", "") or "none")
        for raw in page.hits:
            mapped = file_hit_from_retriever(raw)
            if mapped is not None:
                hits.append(mapped)

    if kind != "all" and len(hits) > limit:
        hits = hits[:limit]

    tier = "none"
    for candidate in ("strong", "strict", "name", "relaxed", "like", "weak"):
        if candidate in tiers:
            tier = candidate
            break
    return {"hits": hits, "tier": tier}
