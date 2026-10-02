from __future__ import annotations

from app.engine.channel_plugins.types import is_channel_origin
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


def conversation_ref_id(raw: str | None) -> str:
    """工具参数里的会话引用 → 会话 id；兼容 ``conversation://id[/消息id]`` 链接写法。"""
    ref = str(raw or "").strip()
    if ref.startswith("conversation://"):
        ref = ref[len("conversation://") :].split("/", 1)[0].split("#", 1)[0]
    return ref.strip()


def _conversation_read_allowed(
    store,
    target_cid: str,
    current_conversation_id: str | None,
) -> bool:
    """会话原文可见性：通道回合只能读本会话；主人回合不可读通道会话。"""
    current_cid = (current_conversation_id or "").strip()
    if current_cid:
        try:
            current_is_channel = is_channel_origin(store.get_origin(current_cid))
        except KeyError:
            current_is_channel = False
    else:
        current_is_channel = False
    try:
        target_is_channel = is_channel_origin(store.get_origin(target_cid))
    except KeyError:
        return True
    if current_is_channel:
        return target_cid == current_cid
    return not target_is_channel


def _resolve_prior_conversation_id(store, current_conversation_id: str | None) -> str | None:
    cid = (current_conversation_id or "").strip()
    if not cid:
        return None
    try:
        prior = store.prior_segment(cid)
    except KeyError:
        return None
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
    cid = conversation_ref_id(conversation_id)
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

    if not _conversation_read_allowed(store, cid, current_conversation_id):
        return _empty(
            conversation_id=cid,
            message_id=mid or None,
            error="forbidden",
            summary="无权读取该会话",
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
