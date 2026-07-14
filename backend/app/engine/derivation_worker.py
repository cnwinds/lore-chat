from __future__ import annotations

from app.engine.conversations import ConversationStore
from app.engine.secrets import mask_secrets
from app.index.conversation_fts import ConversationFTS
from app.index.conversation_vector import ConversationVector
from app.index.message_chunk import chunk_message
from app.index.revision import IndexRevision
from app.logging_config import get_logger
from app.models.llm import LLMClient

_KIND_INDEX_FTS = "index_fts"
_KIND_INDEX_VECTOR = "index_vector"


class DerivationWorker:
    """消费 `derivation_outbox` 任务：脱敏 → 分块 → 写入 ConversationFTS / ConversationVector。"""

    def __init__(
        self,
        conversations: ConversationStore,
        conversation_fts: ConversationFTS,
        *,
        conversation_vector: ConversationVector | None = None,
        llm: LLMClient | None = None,
        index_revision: IndexRevision | None = None,
        chunk_chars: int = 1000,
        overlap: int = 150,
    ):
        self.conversations = conversations
        self.fts = conversation_fts
        self.vector = conversation_vector
        self.llm = llm
        self.revision = index_revision
        self.chunk_chars = chunk_chars
        self.overlap = overlap

    def claim_jobs(self, *, kind: str = _KIND_INDEX_FTS, limit: int = 10) -> list[dict]:
        return self.conversations.claim_outbox(kind=kind, limit=limit, lease_seconds=60)

    def process_job(self, job: dict) -> None:
        self.process_fts_job(job)

    def process_fts_job(self, job: dict) -> None:
        job_id = job["id"]
        message_id = job["source_message_id"]
        try:
            message = self.conversations.get_message(message_id)
            if message is None:
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
                if self.revision:
                    self.revision.bump()
            self.conversations.complete_outbox(job_id)
        except Exception as exc:  # noqa: BLE001
            get_logger("derivation_worker").warning(
                "index_fts 任务失败 job_id=%s message_id=%s", job_id, message_id, exc_info=True
            )
            self.conversations.fail_outbox(job_id, str(exc), backoff=1.0)

    def process_vector_job(self, job: dict) -> None:
        job_id = job["id"]
        message_id = job["source_message_id"]
        if self.vector is None or self.llm is None:
            self.conversations.fail_outbox(job_id, "vector not configured", backoff=1.0)
            return
        try:
            message = self.conversations.get_message(message_id)
            if message is None:
                self.conversations.complete_outbox(job_id)
                return
            masked_text, _ = mask_secrets(message.get("text") or "")
            chunks = chunk_message(masked_text, size=self.chunk_chars, overlap=self.overlap)
            if chunks:
                embs = self.llm.embed([c.text for c in chunks])
                self.vector.upsert_message_chunks(
                    conversation_id=message["conversation_id"],
                    message_id=message_id,
                    role=message.get("role", ""),
                    ts=message.get("ts", ""),
                    conversation_title=message.get("conversation_title", ""),
                    chunks=chunks,
                    embeddings=embs,
                )
                if self.revision:
                    self.revision.bump()
            self.conversations.complete_outbox(job_id)
        except Exception as exc:  # noqa: BLE001
            get_logger("derivation_worker").warning(
                "index_vector 任务失败 job_id=%s message_id=%s", job_id, message_id, exc_info=True
            )
            self.conversations.fail_outbox(job_id, str(exc), backoff=1.0)

    def drain(self, max_jobs: int = 50) -> int:
        done = 0
        for kind in (_KIND_INDEX_FTS, _KIND_INDEX_VECTOR):
            while done < max_jobs:
                jobs = self.conversations.claim_outbox(
                    kind=kind, limit=min(10, max_jobs - done), lease_seconds=60
                )
                if not jobs:
                    break
                for job in jobs:
                    if kind == _KIND_INDEX_FTS:
                        self.process_fts_job(job)
                    else:
                        self.process_vector_job(job)
                    done += 1
        return done
