from __future__ import annotations

import app.sqlite_compat  # noqa: F401
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

from app.index.search_query import compile_search_query, prepare_fts_query
from app.index.types import Hit

__all__ = ["FullTextIndex", "prepare_fts_query", "FtsQueryOutcome"]


@dataclass(frozen=True)
class FtsQueryOutcome:
    hits: list[Hit]
    tier: str  # strict | relaxed | like | none


class FullTextIndex:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        # 允许在 asyncio.to_thread 中访问；用锁串行化写/读
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self.conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS chunks "
                "USING fts5(doc_id, source, body, tokenize='trigram')"
            )
            self.conn.commit()

    def add(self, doc_id: str, chunks: list[str], *, source: str) -> None:
        with self._lock:
            for c in chunks:
                self.conn.execute(
                    "INSERT INTO chunks(doc_id, source, body) VALUES (?, ?, ?)",
                    (doc_id, source, c),
                )
            self.conn.commit()

    def delete(self, doc_id: str) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
            self.conn.commit()

    def query(self, text: str, k: int = 5) -> list[Hit]:
        return self.query_with_tier(text, k=k).hits

    def query_with_tier(self, text: str, *, k: int = 5) -> FtsQueryOutcome:
        text = text.strip()
        if not text:
            return FtsQueryOutcome([], "none")
        compiled = compile_search_query(text)
        with self._lock:
            if compiled.strict_fts:
                rows = self._match(compiled.strict_fts, k)
                if rows:
                    return FtsQueryOutcome(self._rows_to_hits(rows), "strict")
            if compiled.relaxed_fts:
                rows = self._match(compiled.relaxed_fts, k)
                if rows:
                    return FtsQueryOutcome(self._rows_to_hits(rows), "relaxed")
            rows = self._like_fallback(compiled.like_terms, k)
            if rows:
                return FtsQueryOutcome(self._rows_to_hits(rows), "like")
        return FtsQueryOutcome([], "none")

    def _match(self, match: str, k: int) -> list[tuple]:
        if not match:
            return []
        try:
            return self.conn.execute(
                "SELECT doc_id, source, body, bm25(chunks) AS rank "
                "FROM chunks WHERE chunks MATCH ? ORDER BY rank LIMIT ?",
                (match, k),
            ).fetchall()
        except sqlite3.OperationalError:
            return []

    @staticmethod
    def _rows_to_hits(rows: list[tuple]) -> list[Hit]:
        return [
            Hit(doc_id=doc_id, chunk=body, score=-float(rank), source=source)
            for doc_id, source, body, rank in rows
        ]

    def _like_fallback(self, tokens: tuple[str, ...], k: int) -> list[tuple]:
        ordered = sorted(tokens, key=lambda t: len(list(t)), reverse=True)
        for tok in ordered:
            escaped = (
                tok.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            rows = self.conn.execute(
                "SELECT doc_id, source, body, 0.0 AS rank "
                "FROM chunks WHERE body LIKE ? ESCAPE '\\' LIMIT ?",
                (f"%{escaped}%", k),
            ).fetchall()
            if rows:
                return rows
        return []
