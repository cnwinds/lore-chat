from __future__ import annotations

from app.engine.secrets import mask_secrets

_TAIL_MESSAGES = 12


def _empty(*, conversation_id: str | None, message_id: str | None, error: str, summary: str) -> dict:
    return {
        "summary": summary,
        "messages": [],
        "anchor": {
            "message_id": message_id,
            "conversation_id": conversation_id,
            "offset_version": "unicode-codepoint-v1",
        },
        "truncated": False,
        "error": error,
    }


def _resolve_prior_conversation_id(store, current_conversation_id: str | None) -> str | None:
    cid = (current_conversation_id or "").strip()
    if not cid:
        return None
    try:
        role_id = store.get_role_id(cid)
    except KeyError:
        return None
    prior = store.latest_prior_owner_dm(role_id, exclude_conversation_id=cid)
    if not prior:
        return None
    return prior.get("id")


def _pack_messages(rows: list[dict], *, max_chars: int) -> tuple[list[dict], int, bool]:
    out_messages: list[dict] = []
    used = 0
    truncated = False
    for row in rows:
        if (row.get("role") or "") not in ("user", "assistant"):
            continue
        raw_text = row.get("text") or ""
        masked, _ = mask_secrets(raw_text)
        budget = max_chars - used
        if budget <= 0:
            truncated = True
            break
        if len(masked) > budget:
            masked = masked[:budget]
            truncated = True
        used += len(masked)
        out_messages.append(
            {
                "message_id": row["id"],
                "role": row["role"],
                "ts": row.get("ts"),
                "text": masked,
                "offset_version": "unicode-codepoint-v1",
                "source_available": True,
            }
        )
        if truncated:
            break
    return out_messages, used, truncated


def read_conversation_context(
    store,
    *,
    conversation_id: str | None = None,
    message_id: str | None = None,
    before_messages: int = 2,
    after_messages: int = 2,
    max_chars: int = 12000,
    current_conversation_id: str | None = None,
) -> dict:
    cid = (conversation_id or "").strip()
    mid = (message_id or "").strip()
    if not cid:
        if mid:
            cid = store.conversation_id_for_message(mid) or ""
            if not cid:
                return _empty(
                    conversation_id=None,
                    message_id=mid,
                    error="not_found",
                    summary="消息或会话不存在",
                )
        else:
            cid = _resolve_prior_conversation_id(store, current_conversation_id) or ""
            if not cid:
                return _empty(
                    conversation_id=None,
                    message_id=None,
                    error="no_prior",
                    summary="没有可读取的上一会话段",
                )

    title = ""
    older = 0
    if mid:
        before_messages = max(0, min(10, int(before_messages)))
        after_messages = max(0, min(10, int(after_messages)))
        window = store.get_message_window(
            cid,
            mid,
            before_messages=before_messages,
            after_messages=after_messages,
        )
    else:
        window, older = store.load_dialogue_tail(cid, tail=_TAIL_MESSAGES)
    try:
        meta = store.get(cid, tail=0)
        title = (meta.get("title") or "").strip()
    except KeyError:
        title = ""

    out_messages, used, truncated = _pack_messages(window, max_chars=max_chars)
    if older:
        truncated = True
    summary = f"{len(out_messages)} 条消息，约 {used} 字符"
    if title:
        summary = f"{title} · {summary}"
    if older:
        summary = f"{summary}；更早还有 {older} 条"
    return {
        "summary": summary,
        "messages": out_messages,
        "anchor": {
            "message_id": mid or (out_messages[-1]["message_id"] if out_messages else None),
            "conversation_id": cid,
            "offset_version": "unicode-codepoint-v1",
        },
        "truncated": truncated,
        "conversation_title": title or None,
    }
