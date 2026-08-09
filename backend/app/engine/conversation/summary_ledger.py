"""会话归档摘要账本：primary summary 修订与列表。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.engine.conversation.shared import now_iso as _now

if TYPE_CHECKING:
    from app.engine.conversations import ConversationStore


class ConversationSummaryLedger:
    """conversation_summaries 表的读写 seam。

    归档后的记忆调度经 Store 的 intent 钩子，不直接摸 messages / schedule SQL。
    """

    def __init__(self, store: ConversationStore) -> None:
        self._store = store

    def summary_state(self, cid: str) -> tuple[bool, str | None, str | None]:
        row = self._store.conn.execute(
            """
            SELECT doc_path, created_at FROM conversation_summaries
            WHERE conversation_id = ? AND status = 'current' AND is_primary = 1
            ORDER BY revision DESC LIMIT 1
            """,
            (cid,),
        ).fetchone()
        if row is None:
            return False, None, None
        return True, row["doc_path"], row["created_at"]

    def list_unlocked(self, cid: str) -> list[dict]:
        rows = self._store.conn.execute(
            """
            SELECT * FROM conversation_summaries
            WHERE conversation_id = ? ORDER BY revision ASC
            """,
            (cid,),
        ).fetchall()
        return [
            {
                "conversation_id": r["conversation_id"],
                "doc_path": r["doc_path"],
                "revision": r["revision"],
                "covered_through_message_id": r["covered_through_message_id"],
                "status": r["status"],
                "is_primary": bool(r["is_primary"]),
            }
            for r in rows
        ]

    def list_summaries(self, cid: str) -> list[dict]:
        with self._store._lock:
            self._store._conversation_row(cid)
            return self.list_unlocked(cid)

    def mark_stale_unlocked(self, cid: str) -> None:
        self._store.conn.execute(
            """
            UPDATE conversation_summaries SET status = 'stale'
            WHERE conversation_id = ? AND status = 'current'
            """,
            (cid,),
        )

    def record_primary_unlocked(
        self,
        cid: str,
        summary_path: str,
        *,
        covered_through_message_id: str | None,
        at: str,
    ) -> None:
        """仅写 conversation_summaries + 清 indexed_dirty（调用方已持锁）。"""
        store = self._store
        store.conn.execute(
            """
            UPDATE conversation_summaries SET is_primary = 0
            WHERE conversation_id = ? AND is_primary = 1
            """,
            (cid,),
        )
        max_rev = store.conn.execute(
            """
            SELECT COALESCE(MAX(revision), 0) AS n FROM conversation_summaries
            WHERE conversation_id = ? AND doc_path = ?
            """,
            (cid, summary_path),
        ).fetchone()["n"]
        store.conn.execute(
            """
            INSERT INTO conversation_summaries(
                conversation_id, doc_path, revision, covered_through_message_id,
                status, is_primary, created_at
            ) VALUES (?, ?, ?, ?, 'current', 1, ?)
            """,
            (
                cid,
                summary_path,
                int(max_rev) + 1,
                covered_through_message_id,
                at,
            ),
        )
        store.conn.execute(
            "UPDATE conversations SET indexed_dirty = 0, updated_at = ? WHERE id = ?",
            (at, cid),
        )

    def mark_summarized(self, cid: str, summary_path: str) -> None:
        store = self._store
        with store._lock:
            store._conversation_row(cid)
            at = _now()
            covered = store.latest_message_id_unlocked(cid)
            self.record_primary_unlocked(
                cid,
                summary_path,
                covered_through_message_id=covered,
                at=at,
            )
            store.notify_archived_unlocked(cid)
            store.conn.commit()
