from __future__ import annotations

import sqlite3
from pathlib import Path

from app.index.types import Hit


class FullTextIndex:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS chunks "
            "USING fts5(doc_id, source, body, tokenize='trigram')"
        )
        self.conn.commit()

    def add(self, doc_id: str, chunks: list[str], *, source: str) -> None:
        for c in chunks:
            self.conn.execute(
                "INSERT INTO chunks(doc_id, source, body) VALUES (?, ?, ?)",
                (doc_id, source, c),
            )
        self.conn.commit()

    def delete(self, doc_id: str) -> None:
        self.conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        self.conn.commit()

    def query(self, text: str, k: int = 5) -> list[Hit]:
        text = text.strip()
        if not text:
            return []
        rows = self.conn.execute(
            "SELECT doc_id, source, body, bm25(chunks) AS rank "
            "FROM chunks WHERE chunks MATCH ? ORDER BY rank LIMIT ?",
            (text, k),
        ).fetchall()
        hits: list[Hit] = []
        for doc_id, source, body, rank in rows:
            hits.append(Hit(doc_id=doc_id, chunk=body, score=-float(rank), source=source))
        return hits
