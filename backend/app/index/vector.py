from __future__ import annotations

from pathlib import Path

import chromadb

from app.index.types import Hit


class VectorIndex:
    def __init__(self, path: str | Path):
        Path(path).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(path))
        self._col = self._client.get_or_create_collection(
            name="kbs", metadata={"hnsw:space": "cosine"}
        )

    def add(
        self,
        doc_id: str,
        chunks: list[str],
        embeddings: list[list[float]],
        *,
        source: str,
    ) -> None:
        if not chunks:
            return
        ids = [f"{doc_id}::{i}" for i in range(len(chunks))]
        metadatas = [{"doc_id": doc_id, "source": source} for _ in chunks]
        self._col.add(ids=ids, documents=chunks, embeddings=embeddings, metadatas=metadatas)

    def delete(self, doc_id: str) -> None:
        self._col.delete(where={"doc_id": doc_id})

    def query(self, embedding: list[float], k: int = 5) -> list[Hit]:
        res = self._col.query(query_embeddings=[embedding], n_results=k)
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
