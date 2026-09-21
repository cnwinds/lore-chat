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


def should_inject_onboarding_layer(
    role: dict,
    messages: list[dict],
    *,
    client_message_id: str | None = None,
) -> bool:
    """引导长提示只在 kickoff 或尚无主人真实发言时注入，不跟每条后续消息重复。"""
    if role.get("onboarding_status") != "active":
        return False
    if is_onboarding_kickoff_id(client_message_id):
        return True
    return not _has_real_user_message(messages)


def build_onboarding_layer(role_name: str) -> str:
    name = (role_name or "").strip() or "角色"
    return f"""[角色引导]

你正在协助用户完成角色「{name}」的职责与人设定义。

引导原则：
- 角色先开口：新角色创建后不要空等主人先说话，立刻简短自我介绍并问第一个问题
- 每次只问一个问题，保持简短；若提供选项，必须调用 ask_user，不要把选项写进正文
- 选项若不是完整答案、需要主人写出具体内容，将该项 input 设为 true；主人会在卡片里写完再提交。已写在卡片里的内容就是答案，不要再为同一问题追问一遍
- 逐步了解：职责范围、典型输出、边界约束、语气风格
- 询问是否需要定时任务（例如每日总结、周报提醒等）
- 根据对话整理出一份人设草案（system_prompt）
- 向用户展示草案，待确认后调用 finalize_role_onboarding 完成引导（写入角色设置中的人设）
- 在用户确认前，不要擅自调用 update_role 修改 system_prompt

示例流程：
1. 用 ask_user 问职责方向（研究分析 / 内容创作 / 任务管理）
2. 用 ask_user 问输出形式（简报 / 详细报告 / 对话式建议）
3. "有什么明确的边界或不做的事吗？"
4. 用 ask_user 问是否需要定时任务（每天提醒 / 周总结 / 暂不需要）
5. 整理草案 → 展示 → 确认 → finalize_role_onboarding

若用户要求跳过引导，告知可以随时在设置中配置，并询问是否调用 update_role(..., onboarding_status="skipped")。"""
