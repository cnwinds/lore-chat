from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

import chromadb

from app.index.message_chunk import MessageChunk


@dataclass
class ConversationVectorHit:
    chunk_id: str
    conversation_id: str
    message_id: str
    role: str
    start_char: int
    end_char: int
    text: str
    score: float
    ts: str = ""
    conversation_title: str = ""
    offset_version: str = "unicode-codepoint-v1"


class ConversationVector:
    """会话消息级向量索引：Chroma collection `conversation_chunks_v2`，upsert 语义。"""

    COLLECTION = "conversation_chunks_v2"

    def __init__(self, path: str | Path):
        self._path = str(path)
        Path(self._path).mkdir(parents=True, exist_ok=True)
        # Chroma 的 SQLite 连接不能跨线程共享；每线程独立 client
        self._local = threading.local()
        self._lock = threading.Lock()

    def _collection(self):
        col = getattr(self._local, "col", None)
        if col is None:
            client = chromadb.PersistentClient(path=self._path)
            col = client.get_or_create_collection(
                name=self.COLLECTION, metadata={"hnsw:space": "cosine"}
            )
            self._local.col = col
        return col

    @staticmethod
    def chunk_id(conversation_id: str, message_id: str, chunk_index: int) -> str:
        return f"conv:{conversation_id}:msg:{message_id}:chunk:{chunk_index}"

    def upsert_message_chunks(
        self,
        *,
        conversation_id: str,
        message_id: str,
        role: str,
        ts: str,
        conversation_title: str,
        chunks: list[MessageChunk],
        embeddings: list[list[float]],
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks/embeddings length mismatch")
        with self._lock:
            col = self._collection()
            existing = col.get(
                where={
                    "$and": [
                        {"conversation_id": conversation_id},
                        {"message_id": message_id},
                    ]
                }
            )
            if existing and existing.get("ids"):
                col.delete(ids=existing["ids"])
            if not chunks:
                return
            ids, docs, metas = [], [], []
            for c, _emb in zip(chunks, embeddings):
                cid = self.chunk_id(conversation_id, message_id, c.index)
                ids.append(cid)
                docs.append(c.text)
                metas.append(
                    {
                        "conversation_id": conversation_id,
                        "message_id": message_id,
                        "role": role,
                        "chunk_index": c.index,
                        "start_char": c.start_char,
                        "end_char": c.end_char,
                        "ts": ts,
                        "conversation_title": conversation_title or "",
                    }
                )
            col.add(ids=ids, documents=docs, embeddings=embeddings, metadatas=metas)

    @staticmethod
    def _conversation_where(
        *,
        conversation_id: str | None,
        exclude_conversation_id: str | None,
    ) -> dict | None:
        if conversation_id:
            return {"conversation_id": conversation_id}
        if exclude_conversation_id:
            return {"conversation_id": {"$ne": exclude_conversation_id}}
        return None

    def query(
        self,
        embedding: list[float],
        k: int = 5,
        *,
        conversation_id: str | None = None,
        exclude_conversation_id: str | None = None,
    ) -> list[ConversationVectorHit]:
        where = self._conversation_where(
            conversation_id=conversation_id,
            exclude_conversation_id=exclude_conversation_id,
        )
        with self._lock:
            kwargs: dict = {"query_embeddings": [embedding], "n_results": max(k, 1)}
            if where:
                kwargs["where"] = where
            res = self._collection().query(**kwargs)
        hits: list[ConversationVectorHit] = []
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        ids = (res.get("ids") or [[]])[0]
        for doc, meta, dist, cid in zip(docs, metas, dists, ids):
            if meta is None:
                continue
            hits.append(
                ConversationVectorHit(
                    chunk_id=cid,
                    conversation_id=meta["conversation_id"],
                    message_id=meta["message_id"],
                    role=meta.get("role") or "",
                    start_char=int(meta["start_char"]),
                    end_char=int(meta["end_char"]),
                    ts=meta.get("ts") or "",
                    conversation_title=meta.get("conversation_title") or "",
                    text=doc or "",
                    score=1.0 - float(dist),
                )
            )
        return hits[:k]

    def delete_conversation(self, conversation_id: str) -> None:
        with self._lock:
            col = self._collection()
            existing = col.get(where={"conversation_id": conversation_id})
            if existing and existing.get("ids"):
                col.delete(ids=existing["ids"])

    def count_for_message(self, conversation_id: str, message_id: str) -> int:
        with self._lock:
            existing = self._collection().get(
                where={
                    "$and": [
                        {"conversation_id": conversation_id},
                        {"message_id": message_id},
                    ]
                }
            )
        return len(existing.get("ids") or [])
