from __future__ import annotations

from app.index.chunk import chunk_text, chunk_starts
from app.index.kb_index import KB_PARTITION, normalize_kb_path
from app.index.partitioned import IndexItem, SearchIndex

_CHUNK_SIZE = 800
_CHUNK_OVERLAP = 100


class Indexer:
    def __init__(
        self,
        search_index: SearchIndex,
        *,
        system_prefixes: tuple[str, ...] = (),
        reindex_full_threshold: int = 4000,
    ):
        self.search_index = search_index
        self.system_prefixes = tuple(system_prefixes)
        self.reindex_full_threshold = reindex_full_threshold

    def _is_system_path(self, doc_id: str) -> bool:
        norm = normalize_kb_path(doc_id)
        return any(norm.startswith(p) for p in self.system_prefixes)

    def _sync_doc_chunks(self, doc_id: str, text: str) -> None:
        doc_id = normalize_kb_path(doc_id)
        if self._is_system_path(doc_id):
            self.search_index.drop_group(KB_PARTITION, doc_id)
            return
        chunks = chunk_text(text)
        if not chunks:
            self.search_index.drop_group(KB_PARTITION, doc_id)
            return
        items = [
            IndexItem(
                item_id=f"{doc_id}::{i}",
                text=c,
                meta={"source": doc_id, "chunk_index": i},
            )
            for i, c in enumerate(chunks)
        ]
        self.search_index.sync_group(KB_PARTITION, doc_id, items)

    def reindex_doc(self, doc_id: str, text: str) -> None:
        self._sync_doc_chunks(doc_id, text)

    def reindex_doc_after_edit(
        self,
        doc_id: str,
        old_body: str,
        new_body: str,
        affected_start: int | None,
        affected_end: int | None,
    ) -> str:
        doc_id = normalize_kb_path(doc_id)
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

        self._sync_doc_chunks(doc_id, new_body)
        return "partial"

    def remove_doc(self, doc_id: str) -> None:
        doc_id = normalize_kb_path(doc_id)
        if doc_id:
            self.search_index.drop_group(KB_PARTITION, doc_id)
