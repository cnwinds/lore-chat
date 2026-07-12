from __future__ import annotations

import threading
from pathlib import Path

import chromadb

from app.index.types import Hit


class VectorIndex:
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
                name="kbs", metadata={"hnsw:space": "cosine"}
            )
            self._local.col = col
        return col

    def add(
        self,
        doc_id: str,
        chunks: list[str],
        embeddings: list[list[float]],
        *,
        source: str,
        start_index: int = 0,
    ) -> None:
        if not chunks:
            return
        ids = [f"{doc_id}::{i}" for i in range(start_index, start_index + len(chunks))]
        metadatas = [{"doc_id": doc_id, "source": source} for _ in chunks]
        with self._lock:
            self._collection().add(
                ids=ids, documents=chunks, embeddings=embeddings, metadatas=metadatas
            )

    def delete_ids(self, ids: list[str]) -> None:
        if not ids:
            return
        with self._lock:
            self._collection().delete(ids=ids)

    def delete(self, doc_id: str) -> None:
        with self._lock:
            self._collection().delete(where={"doc_id": doc_id})

    def query(self, embedding: list[float], k: int = 5) -> list[Hit]:
        with self._lock:
            res = self._collection().query(query_embeddings=[embedding], n_results=k)
        hits: list[Hit] = []
        docs = res.get("documents") or [[]]
        metas = res.get("metadatas") or [[]]
        dists = res.get("distances") or [[]]
        for doc, meta, dist in zip(docs[0], metas[0], dists[0]):
            hits.append(
                Hit(
                    doc_id=meta["doc_id"],
                    chunk=doc,
                    score=1.0 - float(dist),
                    source=meta["source"],
                )
            )
        return hits
