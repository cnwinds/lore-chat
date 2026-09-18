"""共有回合：验实例/角色 → 映射会话 → begin_persisted_turn。

HTTP 不解析 Agent SSE。脚本 `stream: true` 的精简事件由 `public_sse` 投影。
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from collections import deque
from typing import Any

from app.engine.agent.prompts import MODE_API
from app.engine.channel_plugins.errors import ChannelError
from app.engine.channel_plugins.group_policy import (
    compose_im_reply,
    output_flags,
    sandbox_allowed_for,
    should_enqueue_group,
    thread_external_key,
)
from app.engine.channel_plugins.public_sse import iter_public_chat_sse
from app.engine.channel_plugins.media import materialize_media
from app.engine.channel_plugins.types import SCRIPT_API_TYPE_ID, origin_for_type
from app.engine.conversation.shared import TurnInProgress

_log = logging.getLogger(__name__)

_FAIL_TEXT = "本轮处理失败，请稍后再试。"


class ChannelTurnService:
    def __init__(
        self,
        *,
        roles,
        conversations,
        chat_runner,
        instances=None,
        registry=None,
        runtime_store=None,
        kb_path=None,
    ):
        self.roles = roles
        self.conversations = conversations
        self.chat_runner = chat_runner
        self.instances = instances
        self.registry = registry
        self.runtime_store = runtime_store
        self.kb_path = kb_path
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queues: dict[str, deque[Any]] = {}
        self._drain_tasks: dict[str, asyncio.Task] = {}
        self._qlock = threading.Lock()

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        with self._qlock:
            pending = [iid for iid, q in self._queues.items() if q]
        for iid in pending:
            self._schedule_drain(iid)

    def assert_instance_conversation(self, record: dict, cid: str) -> dict:
        try:
            conv = self.conversations.get(cid)
        except KeyError as e:
            raise ChannelError("对话不存在", code="not_found", status=404) from e
        origin = conv.get("origin") or "web"
        from app.engine.channel_plugins.types import is_channel_origin

        if not is_channel_origin(origin):
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

    def begin_chat(
        self,
        *,
        record: dict,
        message: str,
        conversation_id: str | None = None,
        skills: list[str] | None = None,
        title: str | None = None,
        type_id: str = SCRIPT_API_TYPE_ID,
    ) -> tuple[str, dict[str, Any]]:
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

        turn = self._begin(record, cid, text, skills=skills)
        return cid, turn

    async def complete_chat(
        self,
        *,
        record: dict,
        message: str,
        conversation_id: str | None = None,
        skills: list[str] | None = None,
        title: str | None = None,
        timeout_sec: float = 120,
        type_id: str = SCRIPT_API_TYPE_ID,
    ) -> dict[str, Any]:
        cid, turn = self.begin_chat(
            record=record,
            message=message,
            conversation_id=conversation_id,
            skills=skills,
            title=title,
            type_id=type_id,
        )
        wait = min(max(float(timeout_sec or 120), 0.05), 600.0)
        status = await self._wait_turn(turn, timeout_sec=wait)
        payload = self._chat_payload(cid, turn["turn_id"], status=status)
        show_thinking, show_tool_output = output_flags(record)
        if (show_thinking or show_tool_output) and payload.get("message"):
            assistant = payload.get("assistant") or {}
            payload["message"]["content"] = compose_im_reply(
                assistant,
                fallback=(payload["message"].get("content") or ""),
                show_thinking=show_thinking,
                show_tool_output=show_tool_output,
            )
        return payload

    async def iter_chat_sse(
        self,
        *,
        record: dict,
        conversation_id: str,
        turn: dict,
    ):
        """精简 SSE：观测 hub，不解析业务进 HTTP。断开不取消回合。"""
        show_thinking, show_tool_output = output_flags(record)
        turn_id = turn["turn_id"]
        if turn.get("status", "running") != "running":
            source = self.chat_runner.replay_turn(turn)
        else:
            # hub seq 从 0 起；after_seq 是「已见最后一条」，-1 才能重放首事件。
            source = self.chat_runner.observe_turn(
                conversation_id, turn_id, after_seq=-1
            )

        def _done_payload() -> dict[str, Any]:
            row = self.conversations.get_turn(turn_id)
            status = str((row or {}).get("status") or turn.get("status") or "complete")
            return self._chat_payload(conversation_id, turn_id, status=status)

        async for ev in iter_public_chat_sse(
            source,
            conversation_id=conversation_id,
            turn_id=turn_id,
            show_thinking=show_thinking,
            show_tool_output=show_tool_output,
            done_payload=_done_payload,
        ):
            yield ev

    def enqueue_now(self, event) -> dict[str, Any]:
        """先处理入站（去重/排队），回合异步。不对平台 409。"""
        instance_id = getattr(event, "instance_id", None) or ""
        if not instance_id:
            return {"status": "ignored", "reason": "no_instance"}
        text = (getattr(event, "text", None) or "").strip()
        attachments = getattr(event, "attachments", None) or []
        media = getattr(event, "media", None) or []
        if not text and not attachments and not media:
            return {"status": "ignored", "reason": "empty"}
        if self.instances is not None:
            try:
                inst = self.instances.get(instance_id)
            except KeyError:
                return {"status": "ignored", "reason": "missing"}
            if not inst.get("enabled"):
                return {"status": "ignored", "reason": "disabled"}
        mapped = False
        if getattr(event, "is_group", False) and self.runtime_store is not None:
            try:
                inst_row = (
                    self.instances.get(instance_id) if self.instances is not None else {}
                )
            except KeyError:
                inst_row = {}
            type_id = (inst_row or {}).get("type_id") or "unknown"
            key = thread_external_key(type_id, instance_id, event)
            mapped = bool(self.runtime_store.get_thread(instance_id, key))
        ok, reason = should_enqueue_group(event, has_mapped_thread=mapped)
        if not ok:
            self._log(
                instance_id,
                kind="inbound_ignored",
                message="忽略未点名的群消息",
                extra={"event_id": event.event_id, "reason": reason},
            )
            return {"status": "ignored", "reason": reason}
        event_id = getattr(event, "event_id", None)
        if event_id and self.runtime_store is not None:
            if not self.runtime_store.mark_event(instance_id, event_id):
                self._log(
                    instance_id,
                    kind="inbound_duplicate",
                    message="重复事件已忽略",
                    extra={"event_id": event_id},
                )
                return {"status": "duplicate"}
        with self._qlock:
            self._queues.setdefault(instance_id, deque()).append(event)
        self._schedule_drain(instance_id)
        return {"status": "accepted"}

    def _schedule_drain(self, instance_id: str) -> None:
        loop = self._loop
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
                self._loop = loop
            except RuntimeError:
                return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            self._ensure_drain(instance_id)
            return
        loop.call_soon_threadsafe(self._ensure_drain, instance_id)

    def _ensure_drain(self, instance_id: str) -> None:
        task = self._drain_tasks.get(instance_id)
        if task is not None and not task.done():
            return
        loop = self._loop
        if loop is None:
            return
        self._drain_tasks[instance_id] = loop.create_task(
            self._drain(instance_id), name=f"channel-drain-{instance_id}"
        )

    async def _drain(self, instance_id: str) -> None:
        while True:
            with self._qlock:
                queue = self._queues.get(instance_id)
                event = queue.popleft() if queue else None
            if event is None:
                break
            try:
                await self._run_event(event)
            except Exception:
                _log.exception("channel drain failed instance=%s", instance_id)
                self._log(
                    instance_id,
                    kind="turn_failed",
                    level="error",
                    message="回合执行失败",
                    extra={"event_id": getattr(event, "event_id", None)},
                )
        with self._qlock:
            leftover = bool(self._queues.get(instance_id))
            current = asyncio.current_task()
            if self._drain_tasks.get(instance_id) is current:
                self._drain_tasks.pop(instance_id, None)
        if leftover:
            self._ensure_drain(instance_id)

    async def _run_event(self, event) -> None:
        if self.instances is None:
            return
        inst = self.instances.get_internal(event.instance_id)
        role_id = inst.get("role_id") or ""
        if not role_id:
            raise ChannelError("通道未绑定角色", status=500)
        try:
            self.roles.get(role_id)
        except KeyError as e:
            raise ChannelError("通道角色已失效", status=500) from e
        cid = self._map_conversation(inst, event)
        if self.instances is not None:
            self.instances.touch(event.instance_id)
        paths = list(getattr(event, "attachments", None) or [])
        media = list(getattr(event, "media", None) or [])
        if media and self.kb_path:
            adapter = (
                self.registry.get(inst["type_id"]) if self.registry is not None else None
            )
            downloader = None
            if adapter is not None and hasattr(adapter, "download_media"):

                def downloader(item, _adapter=adapter, _inst=inst, _event=event):
                    return _adapter.download_media(_inst, item, event=_event)

            paths.extend(
                materialize_media(
                    self.kb_path,
                    event.instance_id,
                    media,
                    downloader=downloader,
                )
            )
        user_text = (event.text or "").strip()
        if not user_text and paths:
            user_text = "（附件）"
        allow_sandbox = sandbox_allowed_for(inst, event)
        started = time.monotonic()
        try:
            turn = self._begin(
                inst,
                cid,
                user_text,
                attachments=paths or None,
                sandbox_enabled=allow_sandbox,
            )
        except TurnInProgress:
            with self._qlock:
                self._queues.setdefault(event.instance_id, deque()).appendleft(event)
            await asyncio.sleep(0.4)
            return
        status = await self._wait_until_done(turn)
        duration_ms = int((time.monotonic() - started) * 1000)
        payload = self._chat_payload(cid, turn["turn_id"], status=status)
        assistant = payload.get("assistant") or {}
        show_thinking, show_tool_output = output_flags(inst)
        reply = compose_im_reply(
            assistant,
            fallback=((payload.get("message") or {}).get("content") or ""),
            show_thinking=show_thinking,
            show_tool_output=show_tool_output,
        )
        http_status = payload.get("status")
        if http_status == "failed":
            reply = reply or _FAIL_TEXT
            self._log(
                event.instance_id,
                kind="turn_failed",
                level="error",
                message="回合失败",
                duration_ms=duration_ms,
            )
        elif http_status in {"stopped"}:
            self._log(
                event.instance_id,
                kind="turn_done",
                message="回合已停止",
                duration_ms=duration_ms,
            )
            reply = ""
        else:
            self._log(
                event.instance_id,
                kind="turn_done",
                message="回合完成",
                duration_ms=duration_ms,
            )
        if reply:
            await self._send_outbound(inst, event, reply)

    def _map_conversation(self, inst: dict, event) -> str:
        type_id = inst.get("type_id") or SCRIPT_API_TYPE_ID
        key = thread_external_key(type_id, inst.get("id") or "", event)
        cid = None
        if self.runtime_store is not None:
            cid = self.runtime_store.get_thread(inst["id"], key)
        if cid:
            try:
                self.assert_instance_conversation(inst, cid)
                return cid
            except ChannelError:
                cid = None
        if event.is_group:
            title = (event.display_name or "").strip() or f"{type_id} 群"
        else:
            title = (event.display_name or "").strip() or f"{type_id} 私聊"
        cid = self.conversations.create(
            title=title,
            role_id=inst.get("role_id"),
            origin=origin_for_type(type_id),
            api_key_id=inst.get("id"),
            channel_instance_id=inst.get("id"),
        )
        if self.runtime_store is not None:
            self.runtime_store.put_thread(inst["id"], key, cid)
        return cid

    def _begin(
        self,
        record: dict,
        cid: str,
        text: str,
        *,
        skills: list[str] | None = None,
        attachments: list[str] | None = None,
        sandbox_enabled: bool = True,
    ) -> dict:
        catalog = self.catalog_for(skills)
        client_message_id = uuid.uuid4().hex
        try:
            return self.chat_runner.begin_persisted_turn(
                conversation_id=cid,
                user_text=text,
                client_message_id=client_message_id,
                observation_allowed=False,
                doc_context=None,
                primary_doc=None,
                attachments=attachments,
                doc_paths=list(attachments or []),
                skill_catalog=catalog,
                web_enabled=False,
                mode=MODE_API,
                sandbox_enabled=sandbox_enabled,
            )
        except TurnInProgress:
            raise
        except ValueError as e:
            raise ChannelError(str(e)) from e

    async def _send_outbound(self, inst: dict, event, text: str) -> None:
        if self.registry is None:
            return
        adapter = self.registry.get(inst["type_id"])
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                await asyncio.to_thread(
                    adapter.send_outbound,
                    inst,
                    text,
                    chat_id=event.external_chat_id,
                    external_chat_id=event.external_chat_id,
                    open_id=event.external_user_id,
                    external_user_id=event.external_user_id,
                    thread_id=event.external_thread_id,
                    external_thread_id=event.external_thread_id,
                    reply_to_id=event.reply_to_id,
                    is_group=event.is_group,
                    extra=getattr(event, "extra", None) or {},
                    session_webhook=(getattr(event, "extra", None) or {}).get(
                        "session_webhook"
                    ),
                )
                return
            except Exception as e:
                last_error = e
                self._log(
                    inst["id"],
                    kind="outbound_retry" if attempt < 2 else "outbound_error",
                    level="error" if attempt >= 2 else "warn",
                    message=str(e),
                    extra={"attempt": attempt + 1},
                )
                await asyncio.sleep(0.4 * (attempt + 1))
        if last_error:
            _log.warning(
                "channel outbound failed instance=%s err=%s",
                inst.get("id"),
                last_error,
            )

    def _log(self, instance_id: str, **kwargs) -> None:
        if self.runtime_store is None:
            return
        try:
            self.runtime_store.add_log(instance_id, **kwargs)
        except Exception:
            _log.exception("channel log failed instance=%s", instance_id)

    async def _wait_until_done(self, turn: dict) -> str:
        while True:
            status = await self._wait_turn(turn, timeout_sec=30)
            if status != "running":
                return status

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
            "assistant": assistant,
            "message": {
                "id": (assistant or {}).get("id"),
                "role": "assistant",
                "content": (assistant or {}).get("text") or "",
            }
            if assistant or http_status != "running"
            else None,
        }
