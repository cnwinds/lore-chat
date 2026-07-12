from __future__ import annotations

from app.index.vector import VectorIndex
from app.index.fulltext import FullTextIndex
from app.index.chunk import chunk_text
from app.logging_config import get_logger
from app.models.llm import LLMClient


class Indexer:
    def __init__(self, vector: VectorIndex, fulltext: FullTextIndex, llm: LLMClient):
        self.vector = vector
        self.fulltext = fulltext
        self.llm = llm

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
