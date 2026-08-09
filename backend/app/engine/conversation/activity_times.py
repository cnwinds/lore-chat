"""会话活跃时间：侧栏 updated_at 与记忆 CAS 时钟的修复。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.engine.conversations import ConversationStore


def repair_activity_times(store: ConversationStore) -> int:
    """按消息 / 回合 / 归档摘要真实时间回写侧栏与 CAS 时钟。

    - ``updated_at``：messages / turns / primary summary（保留归档抬高）
    - ``last_user_message_at``：经 ``MemoryExtractSchedule`` 回写为
      ``MAX(turns.started_at)``，与 ``begin_turn`` 的 CAS 语义对齐

    返回更新的会话行数。
    """
    with store._lock:
        rows = store.conn.execute(
            "SELECT id, created_at FROM conversations"
        ).fetchall()
        n = 0
        schedule = store.memory_schedule
        for row in rows:
            cid = row["id"]
            activity = store.conn.execute(
                """
                SELECT MAX(t) AS t FROM (
                    SELECT ts AS t FROM messages WHERE conversation_id = ?
                    UNION ALL
                    SELECT started_at AS t FROM turns WHERE conversation_id = ?
                    UNION ALL
                    SELECT finalized_at AS t FROM turns
                    WHERE conversation_id = ? AND finalized_at IS NOT NULL
                    UNION ALL
                    SELECT created_at AS t FROM conversation_summaries
                    WHERE conversation_id = ?
                      AND status = 'current'
                      AND is_primary = 1
                )
                """,
                (cid, cid, cid, cid),
            ).fetchone()["t"]
            last_user = store.conn.execute(
                """
                SELECT MAX(started_at) AS t FROM turns
                WHERE conversation_id = ?
                """,
                (cid,),
            ).fetchone()["t"]
            updated_at = activity or row["created_at"]
            store.conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (updated_at, cid),
            )
            schedule.restore_last_user_message_at_unlocked(cid, last_user)
            n += 1
        store.conn.commit()
        return n


__all__ = ["repair_activity_times"]
