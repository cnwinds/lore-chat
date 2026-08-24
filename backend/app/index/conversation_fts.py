from __future__ import annotations

import app.sqlite_compat  # noqa: F401 — FTS5 trigram 需较新 SQLite
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

from app.index.search_query import compile_search_query
from app.index.message_chunk import MessageChunk


@dataclass(frozen=True)
class ConversationFtsOutcome:
    hits: list[ConversationHit]
    tier: str  # strict | relaxed | like | none


@dataclass
class ConversationHit:
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


class ConversationFTS:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock:
            self.conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS conversation_chunks_v2
                USING fts5(
                    chunk_id UNINDEXED,
                    conversation_id UNINDEXED,
                    message_id UNINDEXED,
                    role UNINDEXED,
                    start_char UNINDEXED,
                    end_char UNINDEXED,
                    ts UNINDEXED,
                    conversation_title UNINDEXED,
                    body,
                    tokenize='trigram'
                )
                """
            )
            self.conn.commit()

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
    ) -> None:
        with self._lock:
            self.conn.execute(
                "DELETE FROM conversation_chunks_v2 WHERE conversation_id = ? AND message_id = ?",
                (conversation_id, message_id),
            )
            for c in chunks:
                cid = self.chunk_id(conversation_id, message_id, c.index)
                self.conn.execute(
                    """
                    INSERT INTO conversation_chunks_v2(
                        chunk_id, conversation_id, message_id, role,
                        start_char, end_char, ts, conversation_title, body
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        cid,
                        conversation_id,
                        message_id,
                        role,
                        c.start_char,
                        c.end_char,
                        ts,
                        conversation_title,
                        c.text,
                    ),
                )
            self.conn.commit()

    def delete_conversation(self, conversation_id: str) -> None:
        with self._lock:
            self.conn.execute(
                "DELETE FROM conversation_chunks_v2 WHERE conversation_id = ?",
                (conversation_id,),
            )
            self.conn.commit()

    def delete_message(self, conversation_id: str, message_id: str) -> None:
        with self._lock:
            self.conn.execute(
                "DELETE FROM conversation_chunks_v2 WHERE conversation_id = ? AND message_id = ?",
                (conversation_id, message_id),
            )
            self.conn.commit()

    def covered_ranges(self, conversation_id: str, message_id: str) -> list[tuple[int, int]]:
        """已入库的 (start_char, end_char) 区间，供回填任务判断某条消息是否已完整覆盖。"""
        with self._lock:
            rows = self.conn.execute(
                """
                SELECT start_char, end_char FROM conversation_chunks_v2
                WHERE conversation_id = ? AND message_id = ?
                """,
                (conversation_id, message_id),
            ).fetchall()
        return [(int(r[0]), int(r[1])) for r in rows]

    @staticmethod
    def _conversation_filter(
        *,
        conversation_id: str | None,
        exclude_conversation_id: str | None,
    ) -> tuple[str, tuple]:
        if conversation_id:
            return " AND conversation_id = ?", (conversation_id,)
        if exclude_conversation_id:
            return " AND conversation_id != ?", (exclude_conversation_id,)
        return "", ()

    def query(
        self,
        text: str,
        k: int = 5,
        *,
        conversation_id: str | None = None,
        exclude_conversation_id: str | None = None,
    ) -> list[ConversationHit]:
        return self.query_with_tier(
            text,
            k=k,
            conversation_id=conversation_id,
            exclude_conversation_id=exclude_conversation_id,
        ).hits

    def query_with_tier(
        self,
        text: str,
        k: int = 5,
        *,
        conversation_id: str | None = None,
        exclude_conversation_id: str | None = None,
    ) -> ConversationFtsOutcome:
        text = text.strip()
        if not text:
            return ConversationFtsOutcome([], "none")
        compiled = compile_search_query(text)
        cid_filter, params_suffix = self._conversation_filter(
            conversation_id=conversation_id,
            exclude_conversation_id=exclude_conversation_id,
        )
        with self._lock:
            if compiled.strict_fts:
                rows = self._match(
                    compiled.strict_fts, k, cid_filter, params_suffix
                )
                if rows:
                    return ConversationFtsOutcome(self._rows_to_hits(rows), "strict")
            if compiled.relaxed_fts:
                rows = self._match(
                    compiled.relaxed_fts, k, cid_filter, params_suffix
                )
                if rows:
                    return ConversationFtsOutcome(self._rows_to_hits(rows), "relaxed")
            rows = self._like_fallback(
                compiled.like_terms, k, cid_filter, params_suffix
            )
            if rows:
                return ConversationFtsOutcome(self._rows_to_hits(rows), "like")
        return ConversationFtsOutcome([], "none")

    def _match(
        self,
        match: str,
        k: int,
        cid_filter: str,
        params_suffix: tuple,
    ) -> list[tuple]:
        if not match:
            return []
        try:
            return self.conn.execute(
                f"""
                SELECT chunk_id, conversation_id, message_id, role,
                       start_char, end_char, ts, conversation_title, body,
                       bm25(conversation_chunks_v2) AS rank
                FROM conversation_chunks_v2
                WHERE conversation_chunks_v2 MATCH ?{cid_filter}
                ORDER BY rank LIMIT ?
                """,
                (match, *params_suffix, k),
            ).fetchall()
        except sqlite3.OperationalError:
            return []

    @staticmethod
    def _rows_to_hits(rows: list[tuple]) -> list[ConversationHit]:
        return [
            ConversationHit(
                chunk_id=r[0],
                conversation_id=r[1],
                message_id=r[2],
                role=r[3],
                start_char=int(r[4]),
                end_char=int(r[5]),
                ts=r[6] or "",
                conversation_title=r[7] or "",
                text=r[8],
                score=-float(r[9]),
            )
            for r in rows
        ]

    def _like_fallback(
        self,
        tokens: tuple[str, ...],
        k: int,
        cid_filter: str,
        params_suffix: tuple,
    ) -> list[tuple]:
        ordered = sorted(tokens, key=lambda t: len(list(t)), reverse=True)
        for tok in ordered:
            escaped = (
                tok.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            rows = self.conn.execute(
                f"""
                SELECT chunk_id, conversation_id, message_id, role,
                       start_char, end_char, ts, conversation_title, body,
                       0.0 AS rank
                FROM conversation_chunks_v2
                WHERE body LIKE ? ESCAPE '\\'{cid_filter}
                LIMIT ?
                """,
                (f"%{escaped}%", *params_suffix, k),
            ).fetchall()
            if rows:
                return rows
        return []
