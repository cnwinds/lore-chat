from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

from app.index.fulltext import prepare_fts_query
from app.index.message_chunk import MessageChunk


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

    def query(self, text: str, k: int = 5) -> list[ConversationHit]:
        text = text.strip()
        if not text:
            return []
        match = prepare_fts_query(text)
        with self._lock:
            try:
                rows = self.conn.execute(
                    """
                    SELECT chunk_id, conversation_id, message_id, role,
                           start_char, end_char, body, bm25(conversation_chunks_v2) AS rank
                    FROM conversation_chunks_v2
                    WHERE conversation_chunks_v2 MATCH ?
                    ORDER BY rank LIMIT ?
                    """,
                    (match, k),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
            # Trigram MATCH ignores queries shorter than 3 codepoints (SQLite FTS5).
            if not rows and len(list(text)) < 3:
                escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                rows = self.conn.execute(
                    """
                    SELECT chunk_id, conversation_id, message_id, role,
                           start_char, end_char, body, 0.0 AS rank
                    FROM conversation_chunks_v2
                    WHERE body LIKE ? ESCAPE '\\'
                    LIMIT ?
                    """,
                    (f"%{escaped}%", k),
                ).fetchall()
        return [
            ConversationHit(
                chunk_id=r[0],
                conversation_id=r[1],
                message_id=r[2],
                role=r[3],
                start_char=int(r[4]),
                end_char=int(r[5]),
                text=r[6],
                score=-float(r[7]),
            )
            for r in rows
        ]
