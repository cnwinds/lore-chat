"""新角色引导：创建后由角色先开口，而不是等主人先说话。"""

from __future__ import annotations

import logging
from typing import Any

from app.engine.conversation.shared import TurnInProgress

log = logging.getLogger("uvicorn.error")

ONBOARDING_KICKOFF_PREFIX = "onboarding-kickoff:"
ONBOARDING_KICKOFF_USER_TEXT = (
    "（系统）这个角色刚创建。请主动开口：用一两句说明你将协助定义职责与人设，"
    "然后只问第一个问题——这个角色主要负责什么。"
)


def onboarding_kickoff_client_message_id(role_id: str) -> str:
    return f"{ONBOARDING_KICKOFF_PREFIX}{role_id}"


def is_onboarding_kickoff_id(client_message_id: str | None) -> bool:
    return str(client_message_id or "").startswith(ONBOARDING_KICKOFF_PREFIX)


def maybe_kickoff_role_onboarding(container: Any, role_id: str) -> dict | None:
    """空 tip 且引导仍为 active 时，发起一轮隐藏触发，让角色先问职责。

    同一 ``onboarding-kickoff:{role_id}`` 可重入：running 则附着，已完成则不再开新回合。
    """
    roles = getattr(container, "roles", None)
    conversations = getattr(container, "conversations", None)
    chat_runner = getattr(container, "chat_runner", None)
    settings = getattr(container, "settings", None)
    if roles is None or conversations is None or chat_runner is None:
        return None
    try:
        role = roles.get(role_id)
    except KeyError:
        return None
    if role.get("is_default"):
        return None
    if role.get("onboarding_status") != "active":
        return None

    idle = float(getattr(settings, "continuity_idle_hours", 6) or 6)
    cid, _created = conversations.ensure_active_conversation(
        role_id, idle_hours=idle
    )
    if conversations.role_has_running_turn(role_id):
        return None

    if _role_has_real_user_message(conversations, role_id):
        return None

    client_message_id = onboarding_kickoff_client_message_id(role_id)
    try:
        return chat_runner.begin_persisted_turn(
            conversation_id=cid,
            user_text=ONBOARDING_KICKOFF_USER_TEXT,
            client_message_id=client_message_id,
            observation_allowed=False,
            doc_context=None,
            primary_doc=None,
            attachments=None,
            doc_paths=[],
            skill_catalog=None,
            web_enabled=False,
        )
    except TurnInProgress:
        return None
    except Exception:
        log.exception("role onboarding kickoff failed role=%s cid=%s", role_id, cid)
        return None


def _role_has_real_user_message(conversations: Any, role_id: str) -> bool:
    """任一会话里已有主人自己的发言，则不再自动开口。"""
    try:
        items = conversations.list_all(role_id=role_id)
    except Exception:
        return False
    for item in items:
        try:
            conv = conversations.get(item["id"])
        except KeyError:
            continue
        if _has_real_user_message(conv.get("messages") or []):
            return True
    return False


def _has_real_user_message(messages: list[dict]) -> bool:
    for m in messages:
        if m.get("role") != "user":
            continue
        if is_onboarding_kickoff_id(m.get("client_message_id")):
            continue
        if (m.get("text") or "").strip() or m.get("attachments"):
            return True
    return False
