from __future__ import annotations

import sqlite3
from pathlib import Path

from app.index.types import Hit


def prepare_fts_query(text: str, *, max_len: int = 300) -> str:
    """将自由文本转为 FTS5 MATCH 短语，避免 `、* 等字符触发语法错误。"""
    text = " ".join(text.split())
    if not text:
        return ""
    if len(text) > max_len:
        text = text[:max_len]
    escaped = text.replace('"', '""')
    return f'"{escaped}"'


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
        match = prepare_fts_query(text)
        try:
            rows = self.conn.execute(
                "SELECT doc_id, source, body, bm25(chunks) AS rank "
                "FROM chunks WHERE chunks MATCH ? ORDER BY rank LIMIT ?",
                (match, k),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        hits: list[Hit] = []
        for doc_id, source, body, rank in rows:
            hits.append(Hit(doc_id=doc_id, chunk=body, score=-float(rank), source=source))
        return hits
