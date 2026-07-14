from __future__ import annotations

from app.engine.secrets import mask_secrets


def read_conversation_context(
    store,
    *,
    conversation_id: str,
    message_id: str,
    before_messages: int = 2,
    after_messages: int = 2,
    max_chars: int = 12000,
) -> dict:
    before_messages = max(0, min(10, int(before_messages)))
    after_messages = max(0, min(10, int(after_messages)))
    window = store.get_message_window(
        conversation_id,
        message_id,
        before_messages=before_messages,
        after_messages=after_messages,
    )
    out_messages: list[dict] = []
    used = 0
    truncated = False
    for row in window:
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
        out_messages.append({
            "message_id": row["id"],
            "role": row["role"],
            "ts": row.get("ts"),
            "text": masked,
            "offset_version": "unicode-codepoint-v1",
            "source_available": True,
        })
        if truncated:
            break
    return {
        "summary": f"{len(out_messages)} 条消息，约 {used} 字符",
        "messages": out_messages,
        "anchor": {
            "message_id": message_id,
            "conversation_id": conversation_id,
            "offset_version": "unicode-codepoint-v1",
        },
        "truncated": truncated,
    }
