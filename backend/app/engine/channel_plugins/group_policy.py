"""群/频道入站口径：仅 @ 或引用才开回合；群默认关沙箱直到发送者白名单。"""

from __future__ import annotations

from typing import Any


def parse_allow_senders(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = raw.replace("\n", ",").replace(";", ",").split(",")
        return [item.strip() for item in parts if item.strip()]
    if isinstance(raw, (list, tuple, set)):
        out: list[str] = []
        for item in raw:
            text = str(item or "").strip()
            if text:
                out.append(text)
        return out
    return []


def sandbox_allowed_for(instance: dict[str, Any] | None, event) -> bool:
    """私聊允许沙箱；群聊仅当发送者在实例白名单。"""
    if not getattr(event, "is_group", False):
        return True
    cfg = (instance or {}).get("config") or {}
    allow = parse_allow_senders(cfg.get("sandbox_allow_senders"))
    sender = (getattr(event, "external_user_id", None) or "").strip()
    return bool(sender) and sender in allow


def should_enqueue_group(event, *, has_mapped_thread: bool = False) -> tuple[bool, str]:
    """群消息：被 @、被引用、或落在已映射 thread 里才收。"""
    if not getattr(event, "is_group", False):
        return True, "dm"
    if getattr(event, "mentioned_bot", False):
        return True, "mention"
    if getattr(event, "quoted", False):
        return True, "quote"
    if has_mapped_thread:
        return True, "thread"
    return False, "group_bare"


def thread_external_key(type_id: str, instance_id: str, event) -> str:
    if getattr(event, "is_group", False):
        chat = getattr(event, "external_chat_id", None) or "unknown"
        thread = getattr(event, "external_thread_id", None) or ""
        if thread:
            return f"{type_id}:{instance_id}:group:{chat}:{thread}"
        return f"{type_id}:{instance_id}:group:{chat}"
    user = (
        getattr(event, "external_user_id", None)
        or getattr(event, "external_chat_id", None)
        or "unknown"
    )
    return f"{type_id}:{instance_id}:dm:{user}"


def _walk_blocks(blocks: list | None):
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        yield block
        yield from _walk_blocks(block.get("children") or [])


def format_needs_input(assistant: dict | None) -> str | None:
    """ask_user / 沙箱确认 → IM 纯文本。"""
    if not assistant:
        return None
    for block in _walk_blocks(assistant.get("timeline")):
        awaiting = block.get("awaiting_user") or block.get("awaiting_confirm")
        options = block.get("options")
        question = (block.get("question") or "").strip()
        if not awaiting and not (question and isinstance(options, list) and options):
            if block.get("tool") not in {"ask_user", "sandbox_run"}:
                continue
            if not (question and options):
                continue
        if not question:
            question = (block.get("summary") or "需要你确认").strip() or "需要你确认"
        lines = [question]
        if isinstance(options, list):
            for idx, opt in enumerate(options, 1):
                if isinstance(opt, dict):
                    label = str(opt.get("label") or opt.get("id") or "").strip()
                else:
                    label = str(opt or "").strip()
                if label:
                    lines.append(f"{idx}. {label}")
        lines.append("请回复选项，或到 Lore Chat 网页确认。")
        return "\n".join(lines)
    return None


def compose_im_reply(assistant: dict | None, *, fallback: str = "") -> str:
    text = ((assistant or {}).get("text") or "").strip()
    prompt = format_needs_input(assistant)
    if prompt:
        if text and text not in prompt:
            return f"{text}\n\n{prompt}"
        return prompt
    return text or (fallback or "").strip()


def missing_public_url_detail() -> str:
    return "未配置公网根地址 public_base_url，无法启用 webhook"
