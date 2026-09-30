"""提示词块标签：装配时写入 _parts，发出前剥离，供请求快照分段。"""

from __future__ import annotations

import re
from typing import Any

PARTS_KEY = "_parts"

_CATEGORY_BY_KIND: dict[str, str] = {
    "rules": "rules",
    "mode": "rules",
    "role_collab": "rules",
    "extra": "rules",
    "role": "role",
    "role_cards": "cards",
    "turn_cards": "cards",
    "owner_memory": "memory",
    "skill_catalog": "skill",
    "skill_active": "skill",
    "tray": "context",
    "prefetch": "context",
    "time": "context",
    "history": "history",
    "user_text": "turn",
    "attachment": "turn",
    "inject": "turn",
    "tool_call": "tool_io",
    "tool_result": "tool_io",
    "tool_defs": "tools",
    "unlabeled": "unlabeled",
}

_CATEGORY_ORDER: tuple[str, ...] = (
    "rules",
    "role",
    "cards",
    "memory",
    "skill",
    "context",
    "history",
    "turn",
    "tool_io",
    "tools",
    "unlabeled",
)

_CATEGORY_LABELS: dict[str, str] = {
    "rules": "系统规约",
    "role": "当前角色",
    "cards": "知识卡",
    "memory": "主人记忆",
    "skill": "Skill",
    "context": "工作上下文",
    "history": "历史对话",
    "turn": "本轮消息",
    "tool_io": "工具往返",
    "tools": "工具定义",
    "unlabeled": "未标注",
}

_BRACKET = re.compile(r"^【([^】]+)】")


def category_for_kind(kind: str) -> str:
    return _CATEGORY_BY_KIND.get(kind, "unlabeled")


def category_label(key: str) -> str:
    return _CATEGORY_LABELS.get(key, key)


def category_order_key(key: str) -> int:
    try:
        return _CATEGORY_ORDER.index(key)
    except ValueError:
        return len(_CATEGORY_ORDER)


def speaker_label(content: str, role: str) -> str:
    if role == "assistant":
        return "助手"
    text = (content or "").lstrip()
    if text.startswith("【同伴消息】"):
        return "同伴消息"
    if text.startswith("【系统通知】"):
        return "系统通知"
    return "主人"


def extra_label_from_content(content: str) -> str:
    first = (content or "").strip().splitlines()[0] if content else ""
    m = _BRACKET.match(first.strip())
    if m:
        return m.group(1)
    return "附加指令"


def tag(
    msg: dict,
    kind: str,
    *,
    label: str | None = None,
    text: str | None = None,
) -> dict:
    """给消息整条打一个块，返回同一 dict。"""
    body = text if text is not None else str(msg.get("content") or "")
    if label is None:
        if kind == "extra":
            label = extra_label_from_content(body)
        elif kind == "history":
            label = speaker_label(body, str(msg.get("role") or "user"))
        elif kind == "user_text":
            label = speaker_label(body, "user")
        else:
            label = kind
    parts = list(msg.get(PARTS_KEY) or [])
    parts.append({"kind": kind, "label": label, "text": body})
    msg[PARTS_KEY] = parts
    return msg


def copy_tag_history(msg: dict) -> dict:
    """复制历史消息后打 history 标签。"""
    return tag(dict(msg), "history")


def fallback_parts_for_message(msg: dict) -> list[dict[str, Any]]:
    """采集时无 _parts 的兜底块。"""
    role = str(msg.get("role") or "")
    content = str(msg.get("content") or "")
    if role == "system":
        return [{"kind": "extra", "label": extra_label_from_content(content), "text": content}]
    if role == "assistant":
        return [{"kind": "history", "label": "助手", "text": content}]
    if role == "tool":
        return [{"kind": "tool_result", "label": "结果", "text": content}]
    if role == "user":
        return [
            {
                "kind": "history",
                "label": speaker_label(content, "user"),
                "text": content,
            }
        ]
    return [{"kind": "unlabeled", "label": "未标注", "text": content}]
