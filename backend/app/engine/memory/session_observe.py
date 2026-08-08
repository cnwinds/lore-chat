"""会话定稿观察：dirty / idle / extract / resolve / CAS 收进一个 deep module。"""

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
_SOFT_REJECT = frozenset({"tombstoned", "secret_rejected", "rejected", "inactive"})
_log = get_logger("memory.session_observe")


class SessionMemoryObserve:
    """给定 conversation_id，跑完一次 session_observe（对外小 interface）。"""

    def __init__(
        self,
        conversations: ConversationStore,
        memory_service: MemoryService,
        *,
        extractor: SessionMemoryExtractor | None = None,
        idle_hours: float = 24.0,
    ):
        self.conversations = conversations
        self.schedule = conversations.memory_schedule
        self.memory_service = memory_service
        self.extractor = extractor or RuleBasedSessionExtractor()
        self.idle_hours = idle_hours
        # 与 MemoryService 共用同一 Resolver（写不变式 locality）
        self._resolver = memory_service.resolver

    def mark_dirty(self, conversation_id: str, *, at: str | None = None) -> None:
        self.schedule.mark_dirty(conversation_id, at=at)

    def enqueue(
        self, conversation_id: str, *, immediate: bool = False
    ) -> bool:
        return self.schedule.enqueue_session_observe(
            conversation_id, immediate=immediate
        )

    def mark_dirty_and_enqueue(
        self,
        conversation_ids: list[str],
        *,
        mark_dirty: bool = True,
        immediate: bool = False,
    ) -> int:
        """批量标 dirty 并入队（backfill / 维护入口）。"""
        return self.schedule.batch_mark_dirty_and_enqueue(
            conversation_ids,
            mark_dirty=mark_dirty,
            immediate=immediate,
        )

    def schedule_idle(self, *, limit: int = 20) -> int:
        n = 0
        for row in self.schedule.list_idle_dirty(
            idle_hours=self.idle_hours, limit=limit
        ):
            if self.enqueue(row["id"]):
                n += 1
        return n

    def cancel_legacy_jobs(self) -> int:
        return self.schedule.cancel_legacy_observe_memory()

    def process_session_job(self, job: dict) -> None:
        """兼容旧名 → run_job。"""
        self.run_job(job)

    def run_job(self, job: dict) -> None:
        """消费一条 outbox job（保留 job 形以兼容 claim_outbox）。"""
        job_id = job["id"]
        source = job.get("source_message_id") or ""
        cid = source.removeprefix("conv:") if source.startswith("conv:") else source
        try:
            if not cid:
                self.conversations.complete_outbox(job_id)
                return
            immediate = (job.get("turn_id") or "") == SESSION_OBSERVE_IMMEDIATE
            if not immediate and not self.schedule.is_extract_idle(
                cid, idle_hours=self.idle_hours
            ):
                self._complete_and_requeue_immediate(job_id, cid)
                return
            started_last_user_at = self.schedule.get_last_user_message_at(cid)
            turns = self.conversations.list_dialogue_turns(cid)
            if not any(role == "user" and t.strip() for role, t in turns):
                self.schedule.clear_dirty(
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
            actions = self.extractor.extract(turns, confirmed_summary=confirmed)
            confirmed_landed = False
            hard_failures = 0
            for action in actions:
                out = self._resolver.apply(action, conversation_id=cid)
                if not out.get("ok"):
                    if out.get("error") not in _SOFT_REJECT:
                        hard_failures += 1
                    continue
                fact = out.get("fact") or {}
                if fact.get("status") == "confirmed":
                    confirmed_landed = True

            if confirmed_landed:
                self.conversations.append_system_event(
                    cid,
                    "memory_updated",
                    {
                        "type": "memory_updated",
                        "conversation_id": cid,
                    },
                )
            if hard_failures == 0:
                self.schedule.clear_dirty(
                    cid, expected_last_user_message_at=started_last_user_at
                )
            self._complete_and_requeue_immediate(job_id, cid)
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "session_observe_memory 失败 job_id=%s cid=%s err=%s",
                job_id,
                cid,
                exc,
                exc_info=True,
            )
            self.conversations.fail_outbox(job_id, str(exc), backoff=1.0)
            if cid and self.schedule.consume_immediate_pending(cid):
                self.enqueue(cid, immediate=True)

    def drain(self, max_jobs: int = 20) -> int:
        self.cancel_legacy_jobs()
        self.schedule_idle(limit=max_jobs)
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

    def schedule_idle_sessions(self, *, limit: int = 20) -> int:
        """兼容旧 MemoryWorker 名。"""
        return self.schedule_idle(limit=limit)

    def cancel_legacy_observe_jobs(self) -> int:
        """兼容旧 MemoryWorker 名。"""
        return self.cancel_legacy_jobs()

    def _complete_and_requeue_immediate(self, job_id: str, cid: str) -> None:
        self.conversations.complete_outbox(job_id)
        if cid and self.schedule.consume_immediate_pending(cid):
            self.enqueue(cid, immediate=True)


# 兼容旧名
MemoryWorker = SessionMemoryObserve
