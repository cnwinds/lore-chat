from __future__ import annotations

from app.engine.conversations import ConversationStore
from app.engine.secrets import mask_secrets
from app.index.conversation_fts import ConversationFTS
from app.index.message_chunk import chunk_message
from app.logging_config import get_logger

_KIND_INDEX_FTS = "index_fts"


class DerivationWorker:
    """消费 `derivation_outbox` 任务：脱敏 → 分块 → 写入 ConversationFTS。"""

    def __init__(
        self,
        conversations: ConversationStore,
        conversation_fts: ConversationFTS,
        *,
        chunk_chars: int = 1000,
        overlap: int = 150,
    ):
        self.conversations = conversations
        self.fts = conversation_fts
        self.chunk_chars = chunk_chars
        self.overlap = overlap

    def claim_jobs(self, *, kind: str = _KIND_INDEX_FTS, limit: int = 10) -> list[dict]:
        return self.conversations.claim_outbox(kind=kind, limit=limit, lease_seconds=60)

    def process_job(self, job: dict) -> None:
        job_id = job["id"]
        message_id = job["source_message_id"]
        try:
            message = self.conversations.get_message(message_id)
            if message is None:
                # 消息已被删除（如会话被清除），任务无需再处理。
                self.conversations.complete_outbox(job_id)
                return
            masked_text, _ = mask_secrets(message.get("text") or "")
            chunks = chunk_message(masked_text, size=self.chunk_chars, overlap=self.overlap)
            if chunks:
                self.fts.upsert_message_chunks(
                    conversation_id=message["conversation_id"],
                    message_id=message_id,
                    role=message.get("role", ""),
                    ts=message.get("ts", ""),
                    conversation_title=message.get("conversation_title", ""),
                    chunks=chunks,
                )
            self.conversations.complete_outbox(job_id)
        except Exception as exc:  # noqa: BLE001 - 记录后重试，不让 worker 循环崩溃
            get_logger("derivation_worker").warning(
                "index_fts 任务失败 job_id=%s message_id=%s", job_id, message_id, exc_info=True
            )
            self.conversations.fail_outbox(job_id, str(exc), backoff=1.0)

    def drain(self, max_jobs: int = 50) -> int:
        done = 0
        while done < max_jobs:
            jobs = self.claim_jobs(limit=min(10, max_jobs - done))
            if not jobs:
                break
            for job in jobs:
                self.process_job(job)
                done += 1
        return done
