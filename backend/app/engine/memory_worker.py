from __future__ import annotations

from app.engine.conversation.outbox import SESSION_OBSERVE_IMMEDIATE
from app.engine.conversations import ConversationStore
from app.engine.memory.resolver import SlotResolver
from app.engine.memory.service import MemoryService
from app.engine.memory.session_extractor import (
    RuleBasedSessionExtractor,
    SessionMemoryExtractor,
)
from app.logging_config import get_logger

_KIND_SESSION_OBSERVE = "session_observe_memory"


class MemoryWorker:
    """消费会话级 `session_observe_memory`：整段用户消息 → SlotResolver。"""

    def __init__(
        self,
        conversations: ConversationStore,
        memory_service: MemoryService,
        *,
        extractor: SessionMemoryExtractor | None = None,
        idle_hours: float = 24.0,
    ):
        self.conversations = conversations
        self.memory_service = memory_service
        self.extractor = extractor or RuleBasedSessionExtractor()
        self.idle_hours = idle_hours

    def schedule_idle_sessions(self, *, limit: int = 20) -> int:
        n = 0
        for row in self.conversations.list_idle_dirty_conversations(
            idle_hours=self.idle_hours, limit=limit
        ):
            if self.conversations.enqueue_session_observe(row["id"]):
                n += 1
        return n

    def cancel_legacy_observe_jobs(self) -> int:
        return self.conversations.cancel_legacy_observe_memory()

    def _complete_and_requeue_immediate(self, job_id: str, cid: str) -> None:
        self.conversations.complete_outbox(job_id)
        if cid and self.conversations.consume_memory_immediate_pending_if_dirty(cid):
            self.conversations.enqueue_session_observe(cid, immediate=True)

    def process_session_job(self, job: dict) -> None:
        job_id = job["id"]
        source = job.get("source_message_id") or ""
        cid = source.removeprefix("conv:") if source.startswith("conv:") else source
        try:
            if not cid:
                self.conversations.complete_outbox(job_id)
                return
            # 空闲门闩：非即时任务须在消费时仍满足 idle（续聊后勿定稿抽取）
            immediate = (job.get("turn_id") or "") == SESSION_OBSERVE_IMMEDIATE
            if not immediate and not self.conversations.is_memory_extract_idle(
                cid, idle_hours=self.idle_hours
            ):
                # 归档可能在 claim 后把本任务标成即时待办；勿丢即时性
                self._complete_and_requeue_immediate(job_id, cid)
                return
            # 抽取开始快照：结束后 CAS，避免 running 期间续聊被 clear_dirty 抹掉
            started_last_user_at = self.conversations.get_last_user_message_at(cid)
            user_texts = self.conversations.list_user_messages_text(cid)
            if not any(t.strip() for t in user_texts):
                self.conversations.clear_memory_dirty(
                    cid, expected_last_user_message_at=started_last_user_at
                )
                self._complete_and_requeue_immediate(job_id, cid)
                return

            confirmed = [
                {
                    "slot_key": f["slot_key"],
                    "statement": f["statement"],
                    "category": f.get("category"),
                }
                for f in self.memory_service.store.list_confirmed()
            ]
            actions = self.extractor.extract(user_texts, confirmed_summary=confirmed)
            resolver = SlotResolver(self.memory_service.store)
            confirmed_landed = False
            failures = 0
            for action in actions:
                out = resolver.apply(action, conversation_id=cid)
                if not out.get("ok"):
                    failures += 1
                    continue
                fact = out.get("fact") or {}
                # noop 晋升、merge/replace/new 凡落地 confirmed 都发事件
                if fact.get("status") == "confirmed":
                    confirmed_landed = True

            # 有 confirmed 落地则通知前端；注入改为每轮从 DB 直出，无需落盘。
            # 仅零失败且未续聊才清 dirty（规格 §6.1 / §6.2）。
            if confirmed_landed:
                self.conversations.append_system_event(
                    cid,
                    "memory_updated",
                    {
                        "type": "memory_updated",
                        "conversation_id": cid,
                    },
                )
            if failures == 0:
                self.conversations.clear_memory_dirty(
                    cid, expected_last_user_message_at=started_last_user_at
                )
            self._complete_and_requeue_immediate(job_id, cid)
        except Exception as exc:  # noqa: BLE001
            get_logger("memory_worker").warning(
                "session_observe_memory 失败 job_id=%s cid=%s err=%s",
                job_id,
                cid,
                exc,
                exc_info=True,
            )
            self.conversations.fail_outbox(job_id, str(exc), backoff=1.0)

    def drain(self, max_jobs: int = 20) -> int:
        self.cancel_legacy_observe_jobs()
        self.schedule_idle_sessions(limit=max_jobs)
        done = 0
        while done < max_jobs:
            jobs = self.conversations.claim_outbox(
                kind=_KIND_SESSION_OBSERVE,
                limit=min(10, max_jobs - done),
                lease_seconds=120,
            )
            if not jobs:
                break
            for job in jobs:
                self.process_session_job(job)
                done += 1
        return done
