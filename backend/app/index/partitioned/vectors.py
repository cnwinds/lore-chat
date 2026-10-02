from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from app.closing import close_quietly
from app.index.chroma_client import ThreadLocalChroma, make_persistent_client


def _collection_name(family: str, model: str) -> str:
    digest = hashlib.sha1(model.encode("utf-8")).hexdigest()[:12]
    return f"pidx_{family}_{digest}"


class PartitionedVectors:
    """Chroma 向量：每 (族, 模型) 一集合。"""

    def __init__(self, path: str | Path):
        self._path = str(path)
        Path(self._path).mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._chromas: dict[tuple[str, str], ThreadLocalChroma] = {}

    def _chroma(self, family: str, model: str) -> ThreadLocalChroma:
        key = (family, model)
        with self._lock:
            chroma = self._chromas.get(key)
            if chroma is None:
                name = _collection_name(family, model)
                chroma = ThreadLocalChroma(
                    self._path,
                    name,
                    {"hnsw:space": "cosine", "embed_model": model},
                )
                self._chromas[key] = chroma
        return chroma

    def _close_family(self, family: str) -> None:
        with self._lock:
            keys = [k for k in self._chromas if k[0] == family]
            for key in keys:
                close_quietly(self._chromas.pop(key))

    def _with_existing_collection(
        self,
        family: str,
        model: str,
        fn: Callable[[Any], Any],
        default: Any = None,
    ) -> Any:
        key = (family, model)
        with self._lock:
            chroma = self._chromas.get(key)
        if chroma is not None:
            try:
                return fn(chroma.collection())
            except Exception:
                return default
        name = _collection_name(family, model)
        client = make_persistent_client(self._path)
        try:
            col = client.get_collection(name)
            return fn(col)
        except Exception:
            return default
        finally:
            close_quietly(client)

    def upsert(
        self,
        family: str,
        model: str,
        rows: list[
            tuple[
                str,
                str,
                str,
                list[float],
                Mapping[str, str | int | float | bool],
            ]
        ],
    ) -> None:
        if not rows:
            return
        col = self._chroma(family, model).collection()
        ids, docs, embs, metas = [], [], [], []
        for partition, item_id, text, embedding, item_meta in rows:
            ids.append(f"{partition}#{item_id}")
            docs.append(text)
            embs.append(embedding)
            meta = {**item_meta, "partition": partition, "item_id": item_id}
            metas.append(meta)
        with self._lock:
            col.upsert(
                ids=ids, documents=docs, embeddings=embs, metadatas=metas
            )

    def delete(
        self, family: str, model: str, keys: list[tuple[str, str]]
    ) -> None:
        if not keys:
            return
        ids = [f"{p}#{i}" for p, i in keys]

        def _run(col):
            col.delete(ids=ids)

        self._with_existing_collection(family, model, _run)

    def delete_partition(self, family: str, partition: str) -> None:
        self._close_family(family)
        client = make_persistent_client(self._path)
        prefix = f"pidx_{family}_"
        try:
            collections = client.list_collections()
            for col_info in collections:
                name = (
                    col_info.name
                    if hasattr(col_info, "name")
                    else col_info.get("name")
                )
                if not name or not name.startswith(prefix):
                    continue
                try:
                    col = client.get_collection(name)
                    col.delete(where={"partition": partition})
                except Exception:
                    continue
        finally:
            close_quietly(client)

    @staticmethod
    def _build_chroma_where(
        partitions: list[str],
        eq_ne_filters: Sequence[Any],
    ) -> dict[str, Any] | None:
        clauses: list[dict[str, Any]] = []
        if len(partitions) == 1:
            clauses.append({"partition": partitions[0]})
        else:
            clauses.append({"partition": {"$in": partitions}})
        for flt in eq_ne_filters:
            key = flt.key
            if flt.op == "eq":
                clauses.append({key: flt.value})
            elif flt.op == "ne":
                clauses.append({key: {"$ne": flt.value}})
            elif flt.op == "in":
                clauses.append({key: {"$in": list(flt.value)}})
        if not clauses:
            return None
        if len(clauses) == 1:
            return clauses[0]
        return {"$and": clauses}

    def query(
        self,
        family: str,
        model: str,
        embedding: list[float],
        *,
        partitions: list[str],
        k: int,
        eq_ne_filters: Sequence[Any] = (),
        n_results: int | None = None,
    ) -> list[tuple[str, str, float]]:
        if not partitions:
            return []
        where = self._build_chroma_where(partitions, eq_ne_filters)
        n = max(1, n_results if n_results is not None else k)

        def _run(col):
            kwargs: dict[str, Any] = {
                "query_embeddings": [embedding],
                "n_results": n,
            }
            if where is not None:
                kwargs["where"] = where
            return col.query(**kwargs)

        res = self._with_existing_collection(family, model, _run, default=None)
        if not res:
            return []
        hits: list[tuple[str, str, float]] = []
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        for meta, dist in zip(metas, dists):
            if meta is None:
                continue
            hits.append(
                (
                    meta["partition"],
                    meta["item_id"],
                    1.0 - float(dist),
                )
            )
        return hits

    def drop_collection(self, family: str, model: str) -> None:
        name = _collection_name(family, model)
        key = (family, model)
        with self._lock:
            chroma = self._chromas.pop(key, None)
        if chroma:
            chroma.close()
        client = make_persistent_client(self._path)
        try:
            client.delete_collection(name)
        except Exception:
            pass
        finally:
            close_quietly(client)

    def close(self) -> None:
        with self._lock:
            chromas = list(self._chromas.values())
            self._chromas.clear()
        for c in chromas:
            c.close()
