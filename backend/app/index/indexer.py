from __future__ import annotations

from app.index.vector import VectorIndex
from app.index.fulltext import FullTextIndex
from app.index.chunk import chunk_text, chunk_starts
from app.logging_config import get_logger
from app.models.llm import LLMClient

_CHUNK_SIZE = 800
_CHUNK_OVERLAP = 100


class Indexer:
    def __init__(
        self,
        vector: VectorIndex,
        fulltext: FullTextIndex,
        llm: LLMClient,
        *,
        reindex_full_threshold: int = 4000,
    ):
        self.vector = vector
        self.fulltext = fulltext
        self.llm = llm
        self.reindex_full_threshold = reindex_full_threshold

    def reindex_doc(self, doc_id: str, text: str) -> None:
        self.remove_doc(doc_id)
        chunks = chunk_text(text)
        if not chunks:
            return
        try:
            embeddings = self.llm.embed(chunks)
            self.vector.add(doc_id, chunks, embeddings, source=doc_id)
        except Exception:
            # Chroma 异常时仍保证全文索引可用（归档/写入不应因此失败）
            get_logger("indexer").warning("向量索引失败 doc_id=%s", doc_id, exc_info=True)
        self.fulltext.add(doc_id, chunks, source=doc_id)

    def reindex_doc_after_edit(
        self,
        doc_id: str,
        old_body: str,
        new_body: str,
        affected_start: int | None,
        affected_end: int | None,
    ) -> str:
        stripped = new_body.strip()
        if not stripped:
            self.remove_doc(doc_id)
            return "full"

        if len(stripped) <= self.reindex_full_threshold:
            self.reindex_doc(doc_id, new_body)
            return "full"

        if affected_start is None or affected_end is None:
            self.reindex_doc(doc_id, new_body)
            return "full"

        starts = chunk_starts(new_body, size=_CHUNK_SIZE, overlap=_CHUNK_OVERLAP)
        all_chunks = chunk_text(new_body, size=_CHUNK_SIZE, overlap=_CHUNK_OVERLAP)
        if not all_chunks:
            self.remove_doc(doc_id)
            return "full"

        lo = max(0, affected_start - _CHUNK_OVERLAP)
        hi = min(len(stripped), affected_end + _CHUNK_OVERLAP)

        first_idx = len(starts) - 1
        for i, start in enumerate(starts):
            chunk_end = min(start + _CHUNK_SIZE, len(stripped))
            if start < hi and chunk_end > lo:
                first_idx = i
                break

        affected_len = max(0, affected_end - affected_start)
        if first_idx == 0 and affected_len > len(stripped) * 0.5:
            self.reindex_doc(doc_id, new_body)
            return "full"

        old_chunk_count = len(chunk_text(old_body, size=_CHUNK_SIZE, overlap=_CHUNK_OVERLAP))
        tail_chunks = all_chunks[first_idx:]

        try:
            ids_to_delete = [
                f"{doc_id}::{i}" for i in range(first_idx, old_chunk_count)
            ]
            self.vector.delete_ids(ids_to_delete)
            if tail_chunks:
                embeddings = self.llm.embed(tail_chunks)
                self.vector.add(
                    doc_id,
                    tail_chunks,
                    embeddings,
                    source=doc_id,
                    start_index=first_idx,
                )
        except Exception:
            get_logger("indexer").warning(
                "向量增量索引失败 doc_id=%s，回退全量", doc_id, exc_info=True
            )
            self.reindex_doc(doc_id, new_body)
            return "full"

        self.fulltext.delete(doc_id)
        self.fulltext.add(doc_id, all_chunks, source=doc_id)
        return "partial"

    def remove_doc(self, doc_id: str) -> None:
        try:
            self.vector.delete(doc_id)
        except Exception:
            get_logger("indexer").warning("向量索引失败 doc_id=%s", doc_id, exc_info=True)
        self.fulltext.delete(doc_id)

    @staticmethod
    def conversation_doc_id(cid: str) -> str:
        return f"conv:{cid}"

    def index_conversation(self, cid: str, text: str) -> None:
        """会话只进全文索引（FTS）：零嵌入开销，作为归档前的可检索兜底。"""
        doc_id = self.conversation_doc_id(cid)
        self.fulltext.delete(doc_id)
        chunks = chunk_text(text)
        if not chunks:
            return
        self.fulltext.add(doc_id, chunks, source=doc_id)

    def remove_conversation(self, cid: str) -> None:
        doc_id = self.conversation_doc_id(cid)
        self.fulltext.delete(doc_id)
