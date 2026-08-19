from __future__ import annotations

import app.sqlite_compat  # noqa: F401
import sqlite3
import threading
from pathlib import Path

from app.index.types import Hit


def prepare_fts_query(text: str, *, max_len: int = 300) -> str:
    """将自由文本转为 FTS5 MATCH 表达式。

    - 单个词：整段短语匹配
    - 空白分隔多词：按 OR 拼接（Agent 常把中文关键词用空格堆在一起；
      整段带空格的短语在正文里几乎不存在，会导致 0 命中）
    - trigram 对不足 3 个码点的词几乎无效，多词时优先用 ≥3 字的词
    """
    text = " ".join(text.split())
    if not text:
        return ""
    if len(text) > max_len:
        text = text[:max_len]

    def phrase(part: str) -> str:
        return '"' + part.replace('"', '""') + '"'

    parts = text.split(" ")
    if len(parts) == 1:
        return phrase(parts[0])

    usable = [p for p in parts if len(list(p)) >= 3] or parts
    return " OR ".join(phrase(p) for p in usable)


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
        text = text.strip()
        if not text:
            return []
        match = prepare_fts_query(text)
        with self._lock:
            try:
                rows = self.conn.execute(
                    "SELECT doc_id, source, body, bm25(chunks) AS rank "
                    "FROM chunks WHERE chunks MATCH ? ORDER BY rank LIMIT ?",
                    (match, k),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
            # Trigram MATCH 对不足 3 码点的查询无效；多词全 miss 时也用 LIKE 兜底
            if not rows:
                rows = self._like_fallback(text, k)
        hits: list[Hit] = []
        for doc_id, source, body, rank in rows:
            hits.append(Hit(doc_id=doc_id, chunk=body, score=-float(rank), source=source))
        return hits

    def _like_fallback(self, text: str, k: int) -> list[tuple]:
        tokens = [t for t in text.split() if t] or [text]
        # 长词优先，更可能命中有意义片段
        tokens = sorted(tokens, key=lambda t: len(list(t)), reverse=True)
        for tok in tokens:
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
