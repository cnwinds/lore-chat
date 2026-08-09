"""会话删除：ledger → SQLite purge → 派生索引清理。"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.engine.conversation.outbox import (
    append_deletion_ledger,
    default_deletion_ledger_path,
)
from app.engine.conversation.shared import new_id as _new_id
from app.engine.conversation.shared import now_iso as _now
from app.engine.conversation.shared import dumps_json as _dumps


class ConversationFTSLike(Protocol):
    def delete_conversation(self, conversation_id: str) -> None: ...


class ConversationVectorLike(Protocol):
    def delete_conversation(self, conversation_id: str) -> None: ...


class IndexRevisionLike(Protocol):
    def bump(self) -> int: ...


class IndexerLike(Protocol):
    def remove_conversation(self, cid: str) -> None: ...


class ConversationDeletionWorkflow:
    """删会话且派生索引一致（spec §16）。"""

    def __init__(self, store) -> None:
        self.store = store

    def delete(
        self,
        cid: str,
        *,
        conversation_fts: ConversationFTSLike | None = None,
        conversation_vector: ConversationVectorLike | None = None,
        indexer: IndexerLike | None = None,
        index_revision: IndexRevisionLike | None = None,
        ledger_path: str | Path | None = None,
        delete_summary: bool = True,
    ) -> None:
        store = self.store
        with store._lock:
            store._conversation_row(cid)

        deletion_id = _new_id()
        deleted_at = _now()
        options = {"delete_summary": delete_summary}
        ledger_file = (
            Path(ledger_path)
            if ledger_path
            else default_deletion_ledger_path(store.dir)
        )
        append_deletion_ledger(ledger_file, cid, deletion_id, deleted_at, options)

        with store._lock:
            store._conversation_row(cid)
            store.conn.execute(
                """
                INSERT INTO conversation_deletion_ledger(
                    conversation_id, deletion_id, deleted_at, options_json
                ) VALUES (?, ?, ?, ?)
                """,
                (cid, deletion_id, deleted_at, _dumps(options)),
            )
            store._outbox.cancel_pending_for_conversation(cid, deleted_at)
            store.conn.execute("DELETE FROM turns WHERE conversation_id = ?", (cid,))
            if delete_summary:
                store.conn.execute(
                    "DELETE FROM conversation_summaries WHERE conversation_id = ?",
                    (cid,),
                )
            store.conn.execute("DELETE FROM messages WHERE conversation_id = ?", (cid,))
            store.conn.execute("DELETE FROM conversations WHERE id = ?", (cid,))
            store.conn.commit()

        index_cleared = False
        if conversation_fts is not None:
            conversation_fts.delete_conversation(cid)
            index_cleared = True
        if conversation_vector is not None:
            try:
                conversation_vector.delete_conversation(cid)
            except Exception:
                from app.logging_config import get_logger

                get_logger("conversations").warning(
                    "会话向量索引清理失败 conversation_id=%s", cid, exc_info=True
                )
            index_cleared = True
        if index_revision is not None and index_cleared:
            index_revision.bump()
        if indexer is not None:
            indexer.remove_conversation(cid)
