from __future__ import annotations

from app.engine.conversations import ConversationStore
from app.engine.memory.intake import MemoryIntake
from app.engine.memory.service import MemoryService
from app.logging_config import get_logger

_KIND_OBSERVE_MEMORY = "observe_memory"


class MemoryWorker:
    """消费 `observe_memory` outbox：提取候选 → policy → memory.db。"""

    def __init__(
        self,
        conversations: ConversationStore,
        memory_service: MemoryService,
        *,
        observer: MemoryIntake | None = None,
    ):
        self.conversations = conversations
        self.memory_service = memory_service
        self.intake = observer or MemoryIntake(memory_service.store)

    def process_observe_job(self, job: dict) -> None:
        job_id = job["id"]
        message_id = job["source_message_id"]
        try:
            message = self.conversations.get_message(message_id)
            if message is None:
                self.conversations.complete_outbox(job_id)
                return
            if message.get("role") != "user":
                self.conversations.complete_outbox(job_id)
                return
            text = message.get("text") or ""
            cid = message["conversation_id"]
            result = self.intake.observe_user_message(
                text,
                conversation_id=cid,
                message_id=message_id,
            )
            if result.confirmed_count > 0:
                self.memory_service.render_to_file()
                self.conversations.append_system_event(
                    cid,
                    "memory_updated",
                    {
                        "type": "memory_updated",
                        "conversation_id": cid,
                        "count": result.confirmed_count,
                        "path": self.memory_service.memory_rel,
                    },
                )
            self.conversations.complete_outbox(job_id)
        except Exception as exc:  # noqa: BLE001
            get_logger("memory_worker").warning(
                "observe_memory 任务失败 job_id=%s message_id=%s",
                job_id,
                message_id,
                exc_info=True,
            )
            self.conversations.fail_outbox(job_id, str(exc), backoff=1.0)

    def drain(self, max_jobs: int = 20) -> int:
        done = 0
        while done < max_jobs:
            jobs = self.conversations.claim_outbox(
                kind=_KIND_OBSERVE_MEMORY,
                limit=min(10, max_jobs - done),
                lease_seconds=60,
            )
            if not jobs:
                break
            for job in jobs:
                self.process_observe_job(job)
                done += 1
        return done
