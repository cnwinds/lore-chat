"""对外聊天：人设 + 每 Key 一个隐藏工作角色 + 同步回合。"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from app.engine.agent.prompts import MODE_API
from app.engine.conversation.shared import TurnInProgress
from app.engine.roles import API_ROLE_PREFIX, VISIBILITY_HIDDEN


class OpenApiError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid", status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


class OpenApiService:
    def __init__(self, *, roles, api_keys, conversations, chat_runner):
        self.roles = roles
        self.api_keys = api_keys
        self.conversations = conversations
        self.chat_runner = chat_runner

    def list_personas(self) -> list[dict]:
        return self.roles.list_personas()

    def create_persona(
        self,
        *,
        name: str,
        system_prompt: str = "",
        avatar: str | None = None,
    ) -> dict:
        return self.roles.create_persona(
            name=name, system_prompt=system_prompt, avatar=avatar
        )

    def create_persona_from_role(self, role_id: str) -> dict:
        role = self.roles.get(role_id)
        if role.get("visibility") == VISIBILITY_HIDDEN:
            raise OpenApiError("不能从开放接口角色复制人设")
        return self.roles.create_persona(
            name=role.get("name") or "人设",
            system_prompt=role.get("system_prompt") or "",
            avatar=role.get("avatar"),
        )

    def update_persona(self, persona_id: str, **fields) -> dict:
        return self.roles.update_persona(persona_id, **fields)

    def delete_persona(self, persona_id: str) -> None:
        using = self.api_keys.ids_for_persona(persona_id)
        if using:
            raise OpenApiError("仍有密钥使用此人设，请先吊销密钥")
        self.roles.delete_persona(persona_id)

    def list_keys(self) -> list[dict]:
        out = []
        for key in self.api_keys.list_all():
            out.append(self._enrich_key(key))
        return out

    def _enrich_key(self, key: dict) -> dict:
        item = dict(key)
        persona = None
        pid = key.get("persona_id")
        if pid:
            try:
                persona = self.roles.get_persona(pid)
            except KeyError:
                persona = None
        item["persona"] = persona
        return item

    def create_key(
        self,
        *,
        name: str,
        persona_id: str | None = None,
        persona_name: str | None = None,
        persona_prompt: str = "",
        persona_avatar: str | None = None,
    ) -> dict:
        if persona_id:
            persona = self.roles.get_persona(persona_id)
        else:
            pname = (persona_name or name or "").strip() or "开放接口"
            persona = self.roles.create_persona(
                name=pname,
                system_prompt=persona_prompt or "",
                avatar=persona_avatar,
            )
        key_id = uuid.uuid4().hex[:12]
        role_id = f"{API_ROLE_PREFIX}{key_id}"
        display = f"{persona['name']} · {name.strip()}"
        self.roles.create(
            name=display[:80],
            system_prompt="",
            avatar=persona.get("avatar"),
            role_id=role_id,
            visibility=VISIBILITY_HIDDEN,
            persona_id=persona["id"],
            onboarding_status="completed",
        )
        raw, record = self.api_keys.create(
            name=name,
            persona_id=persona["id"],
            role_id=role_id,
            key_id=key_id,
        )
        return {**self._enrich_key(record), "token": raw}

    def revoke_key(self, key_id: str) -> dict:
        return self._enrich_key(self.api_keys.revoke(key_id))

    def resolve_bearer(self, raw: str) -> dict | None:
        rec = self.api_keys.resolve(raw)
        if rec is None:
            return None
        self.api_keys.touch(rec["id"])
        return rec

    def _assert_key_conversation(self, key: dict, cid: str) -> dict:
        try:
            conv = self.conversations.get(cid)
        except KeyError as e:
            raise OpenApiError("对话不存在", code="not_found", status=404) from e
        if (conv.get("origin") or "web") != "api":
            raise OpenApiError("对话不存在", code="not_found", status=404)
        if conv.get("api_key_id") != key.get("id"):
            raise OpenApiError("对话不存在", code="not_found", status=404)
        return conv

    def _catalog_for(
        self, requested: list[str] | None
    ) -> list[dict[str, str]]:
        from app.engine.enabled_skills import EnabledSkillsError

        try:
            catalog = self.chat_runner.resolve_skill_catalog()
        except EnabledSkillsError as e:
            raise OpenApiError(str(e), code="skills") from e
        if not requested:
            return catalog
        want = {str(x).strip() for x in requested if str(x).strip()}
        if not want:
            return catalog
        filtered = [
            e
            for e in catalog
            if e.get("root") in want or e.get("name") in want
        ]
        if not filtered:
            raise OpenApiError("没有可用的 Skill（与启用集交集为空）")
        return filtered

    def _role_busy(self, role_id: str) -> str | None:
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
        key: dict,
        message: str,
        conversation_id: str | None = None,
        skills: list[str] | None = None,
        title: str | None = None,
        timeout_sec: float = 120,
    ) -> dict[str, Any]:
        text = (message or "").strip()
        if not text:
            raise OpenApiError("message required")
        role_id = key.get("role_id") or ""
        if not role_id:
            raise OpenApiError("密钥未绑定角色", status=500)
        try:
            self.roles.get(role_id)
        except KeyError as e:
            raise OpenApiError("密钥角色已失效", status=500) from e

        busy = self._role_busy(role_id)
        if busy:
            raise TurnInProgress(busy)

        cid = (conversation_id or "").strip() or None
        if cid:
            self._assert_key_conversation(key, cid)
        else:
            cid = self.conversations.create(
                title=(title or "").strip() or None,
                role_id=role_id,
                origin="api",
                api_key_id=key["id"],
            )

        catalog = self._catalog_for(skills)
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
            raise OpenApiError(str(e)) from e

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

    def list_key_conversations(self, key_id: str) -> list[dict]:
        key = self.api_keys.get(key_id)
        role_id = key.get("role_id")
        if not role_id:
            return []
        return self.conversations.list_all(role_id=role_id)
