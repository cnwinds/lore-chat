"""共有回合：验实例/角色 → 映射会话 → begin_persisted_turn。不解析 SSE。"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from app.engine.agent.prompts import MODE_API
from app.engine.channel_plugins.errors import ChannelError
from app.engine.channel_plugins.types import origin_for_type
from app.engine.conversation.shared import TurnInProgress


class ChannelTurnService:
    def __init__(self, *, roles, conversations, chat_runner):
        self.roles = roles
        self.conversations = conversations
        self.chat_runner = chat_runner

    def assert_instance_conversation(self, record: dict, cid: str) -> dict:
        try:
            conv = self.conversations.get(cid)
        except KeyError as e:
            raise ChannelError("对话不存在", code="not_found", status=404) from e
        origin = conv.get("origin") or "web"
        if origin != "api":
            raise ChannelError("对话不存在", code="not_found", status=404)
        inst_id = record.get("id")
        owner = conv.get("channel_instance_id") or conv.get("api_key_id")
        if owner != inst_id and conv.get("api_key_id") != inst_id:
            raise ChannelError("对话不存在", code="not_found", status=404)
        return conv

    def catalog_for(self, requested: list[str] | None) -> list[dict[str, str]]:
        from app.engine.enabled_skills import EnabledSkillsError

        try:
            catalog = self.chat_runner.resolve_skill_catalog()
        except EnabledSkillsError as e:
            raise ChannelError(str(e), code="skills") from e
        if not requested:
            return catalog
        want = {str(x).strip() for x in requested if str(x).strip()}
        if not want:
            return catalog
        filtered = [
            entry
            for entry in catalog
            if entry.get("root") in want or entry.get("name") in want
        ]
        if not filtered:
            raise ChannelError("没有可用的 Skill（与启用集交集为空）")
        return filtered

    def role_busy(self, role_id: str) -> str | None:
        for turn in self.conversations.list_running_turns():
            try:
                if self.conversations.get_role_id(turn["conversation_id"]) == role_id:
                    return turn.get("turn_id") or turn.get("id")
            except KeyError:
                continue
        return None

    async def complete_chat(
        self,
        *,
        record: dict,
        message: str,
        conversation_id: str | None = None,
        skills: list[str] | None = None,
        title: str | None = None,
        timeout_sec: float = 120,
        type_id: str = "script_api",
    ) -> dict[str, Any]:
        text = (message or "").strip()
        if not text:
            raise ChannelError("message required")
        role_id = record.get("role_id") or ""
        if not role_id:
            raise ChannelError("密钥未绑定角色", status=500)
        try:
            self.roles.get(role_id)
        except KeyError as e:
            raise ChannelError("密钥角色已失效", status=500) from e

        busy = self.role_busy(role_id)
        if busy:
            raise TurnInProgress(busy)

        cid = (conversation_id or "").strip() or None
        if cid:
            self.assert_instance_conversation(record, cid)
        else:
            inst_id = record.get("id")
            cid = self.conversations.create(
                title=(title or "").strip() or None,
                role_id=role_id,
                origin=origin_for_type(type_id),
                api_key_id=inst_id,
                channel_instance_id=inst_id,
            )

        catalog = self.catalog_for(skills)
        client_message_id = uuid.uuid4().hex
        try:
            turn = self.chat_runner.begin_persisted_turn(
                conversation_id=cid,
                user_text=text,
                client_message_id=client_message_id,
                observation_allowed=False,
                doc_context=None,
                primary_doc=None,
                attachments=None,
                doc_paths=[],
                skill_catalog=catalog,
                web_enabled=False,
                mode=MODE_API,
            )
        except TurnInProgress:
            raise
        except ValueError as e:
            raise ChannelError(str(e)) from e

        wait = min(max(float(timeout_sec or 120), 0.05), 600.0)
        status = await self._wait_turn(turn, timeout_sec=wait)
        return self._chat_payload(cid, turn["turn_id"], status=status)

    async def _wait_turn(self, turn: dict, *, timeout_sec: float) -> str:
        if turn.get("status", "running") != "running":
            return str(turn.get("status") or "complete")
        hub = self.chat_runner.turn_hub
        at = hub._by_turn.get(turn["turn_id"])
        task = getattr(at, "task", None) if at is not None else None
        if task is None:
            row = self.conversations.get_turn(turn["turn_id"])
            return str((row or {}).get("status") or "running")
        done, _pending = await asyncio.wait({task}, timeout=timeout_sec)
        if task not in done:
            return "running"
        row = self.conversations.get_turn(turn["turn_id"])
        return str((row or {}).get("status") or "complete")

    def _chat_payload(self, cid: str, turn_id: str, *, status: str) -> dict:
        conv = self.conversations.get(cid)
        assistant = None
        for msg in reversed(conv.get("messages") or []):
            if msg.get("role") == "assistant":
                assistant = msg
                break
        http_status = "completed"
        if status == "running":
            http_status = "running"
        elif status in ("interrupted", "stopped"):
            http_status = "stopped"
        elif status not in ("complete", "completed"):
            http_status = "failed"
        return {
            "conversation_id": cid,
            "turn_id": turn_id,
            "status": http_status,
            "message": {
                "id": (assistant or {}).get("id"),
                "role": "assistant",
                "content": (assistant or {}).get("text") or "",
            }
            if assistant or http_status != "running"
            else None,
        }
