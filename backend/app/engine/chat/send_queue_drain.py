"""服务端发送队列 drain：回合结束时由 TurnHub 钩子驱动。

语义（与原客户端编排器对齐）：
- 回合被打断/停止（interrupted / explicit_stop）→ 队列暂停，
  注入中的条目还原为排队（defer），等待用户手动继续；
- 停止原因为 awaiting_user（ask_user / sandbox_confirm 征询）→ 暂停，
  等用户作答后再继续；
- 其余完成态：取队首条目（含合并组）作为新回合自动续发；
- 队首 timing=inject 且仍有运行中的回合 → 服务端注入消费。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.engine.chat.send_queue_store import SendQueueStore
from app.engine.chat.turn_inject import PendingInject

_log = logging.getLogger(__name__)

_DRAIN_DELAY_SEC = 0.6


class SendQueueDrainer:
    def __init__(
        self,
        *,
        store: SendQueueStore,
        chat_runner,
        pending=None,
    ) -> None:
        self.store = store
        self.chat_runner = chat_runner
        self.pending = pending
        self._locks: dict[str, asyncio.Lock] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def lock_for(self, conversation_id: str) -> asyncio.Lock:
        return self._locks.setdefault(
            conversation_id, asyncio.Lock()
        )

    def on_turn_end(
        self, conversation_id: str, turn_status: str | None, stop_reason: str
    ) -> None:
        """TurnHub 回合结束钩子：按结束原因决定暂停或续发。"""
        if stop_reason == "awaiting_user" or turn_status == "interrupted":
            # 征询/中断：暂停自动续发，等用户处理
            self.store.set_paused(conversation_id, True)
            _log.info(
                "send queue paused cid=%s reason=%s",
                conversation_id,
                stop_reason or turn_status,
            )
            return
        self.schedule_drain(conversation_id, delay=_DRAIN_DELAY_SEC)

    def schedule_drain(self, conversation_id: str, delay: float = 0.0) -> None:
        old = self._tasks.get(conversation_id)
        if old is not None and not old.done():
            old.cancel()
        self._tasks[conversation_id] = asyncio.create_task(
            self._drain_after(conversation_id, delay),
            name=f"send-queue-drain-{conversation_id[:8]}",
        )

    async def _drain_after(self, conversation_id: str, delay: float) -> None:
        if delay > 0:
            await asyncio.sleep(delay)
        async with self.lock_for(conversation_id):
            await self.drain(conversation_id)

    def schedule_inject_consume(
        self, conversation_id: str, delay: float = 0.3
    ) -> None:
        """新回合开始后消费队首 inject 条目（如用户手动发起的下一回合）。"""
        self._tasks[conversation_id] = asyncio.create_task(
            self._drain_after(conversation_id, delay),
            name=f"send-queue-inject-{conversation_id[:8]}",
        )

    async def drain(self, conversation_id: str) -> None:
        if self.store.is_paused(conversation_id):
            return
        items = self.store.list_items(conversation_id)
        if not items:
            return
        head = items[0]
        group = self._take_merge_group(items)
        status = self.chat_runner.resolve_active_turn_status(
            conversation_id
        ).get("status")
        if status == "running":
            # 有运行中的回合：inject 条目走服务端注入，其余等待
            if head["timing"] == "inject":
                await self._inject_group(conversation_id, group)
            return
        await self._start_next_turn(conversation_id, group)

    async def consume_inject_if_any(self, conversation_id: str) -> None:
        if self.store.is_paused(conversation_id):
            return
        items = self.store.list_items(conversation_id)
        if not items or items[0]["timing"] != "inject":
            return
        if self.chat_runner.resolve_active_turn_status(
            conversation_id
        ).get("status") != "running":
            return
        await self._inject_group(conversation_id, self._take_merge_group(items))

    def _take_merge_group(
        self, items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        group = [items[0]]
        for item in items[1:]:
            if not group[-1].get("merge_with_next"):
                break
            group.append(item)
        return group

    async def _inject_group(
        self, conversation_id: str, group: list[dict[str, Any]]
    ) -> None:
        text = "\n\n".join(g["text"] for g in group)
        head = group[0]
        try:
            self.chat_runner.enqueue_inject(
                conversation_id,
                PendingInject(
                    text=text,
                    inject_id=head["id"],
                    client_message_id=f"inject:{head['id']}",
                    doc_context=head.get("doc_context"),
                    primary_doc=head.get("primary_doc"),
                    attachments=head.get("attachments"),
                ),
            )
        except Exception as e:
            _log.warning(
                "send queue inject failed cid=%s: %s", conversation_id, e
            )
            self.store.update(head["id"], {"error": str(e)})
            self.store.set_paused(conversation_id, True)
            return
        for g in group:
            self.store.remove(conversation_id, g["id"])

    async def _start_next_turn(
        self, conversation_id: str, group: list[dict[str, Any]]
    ) -> None:
        head = group[0]
        text = "\n\n".join(g["text"] for g in group)
        client_message_id = f"queue:{head['id']}"
        try:
            self.chat_runner.begin_persisted_turn(
                conversation_id=conversation_id,
                user_text=text,
                client_message_id=client_message_id,
                observation_allowed=True,
                doc_context=head.get("doc_context"),
                primary_doc=head.get("primary_doc"),
                attachments=head.get("attachments"),
                doc_paths=[],
                skill_catalog=None,
                web_enabled=bool(head.get("web_enabled")),
            )
        except Exception as e:
            _log.warning(
                "send queue auto-continue failed cid=%s: %s",
                conversation_id,
                e,
            )
            self.store.update(head["id"], {"error": str(e)})
            self.store.set_paused(conversation_id, True)
            return
        for g in group:
            self.store.remove(conversation_id, g["id"])
