"""角色定时任务 worker：到期后在主 event loop 上 begin_persisted_turn。"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from app.engine.conversation.shared import TurnInProgress
from app.engine.rooms.delivery import drain_due_inbound

log = logging.getLogger("uvicorn.error")

_SCHEDULE_WORKER_INTERVAL_SECONDS = 30.0


async def fire_due_role_schedule(container: Any, schedule: dict) -> None:
    """在 uvicorn loop 上触发一条到期定时；有 running turn 则短顺延。"""
    roles = container.roles
    conversations = container.conversations
    chat_runner = container.chat_runner
    settings = container.settings
    sid = schedule["id"]
    role_id = schedule["role_id"]
    try:
        roles.get(role_id)
    except KeyError:
        try:
            roles.schedules.delete(sid)
        except KeyError:
            pass
        return

    if conversations.role_has_running_turn(role_id):
        roles.schedules.defer(sid, minutes=5)
        return

    cid, _created = conversations.ensure_active_conversation(
        role_id,
        idle_hours=float(settings.continuity_idle_hours),
    )
    meta = conversations.get_active_turn_meta(cid)
    if meta.get("status") == "running":
        roles.schedules.defer(sid, minutes=5)
        return

    client_message_id = f"role-schedule:{sid}:{uuid.uuid4().hex[:8]}"
    try:
        chat_runner.begin_persisted_turn(
            conversation_id=cid,
            user_text=schedule["prompt"],
            client_message_id=client_message_id,
            observation_allowed=True,
            doc_context=None,
            primary_doc=None,
            attachments=None,
            doc_paths=[],
            skill_catalog=None,
            web_enabled=False,
        )
    except TurnInProgress:
        roles.schedules.defer(sid, minutes=5)
        return
    except Exception:
        log.exception("role schedule fire failed id=%s role=%s", sid, role_id)
        roles.schedules.defer(sid, minutes=15)
        return

    roles.schedules.mark_ran(sid)


def drain_due_role_schedules(container: Any, loop: asyncio.AbstractEventLoop) -> None:
    """线程侧：列出 due，把 fire 协程投递到主 loop。"""
    due = container.roles.schedules.list_due(limit=10)
    for schedule in due:
        fut = asyncio.run_coroutine_threadsafe(
            fire_due_role_schedule(container, schedule), loop
        )
        try:
            fut.result(timeout=120)
        except Exception:
            log.exception(
                "role schedule drain failed id=%s", schedule.get("id")
            )
    async def _drain_inbound() -> None:
        drain_due_inbound(container)

    try:
        asyncio.run_coroutine_threadsafe(_drain_inbound(), loop).result(timeout=30)
    except Exception:
        log.exception("role inbound drain failed")
