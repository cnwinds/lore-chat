from __future__ import annotations

from app.engine.conversations import ConversationStore


def enqueue_observe_for_retained_messages(
    store: ConversationStore,
    *,
    conversation_id: str | None = None,
) -> int:
    """为 retained 用户消息显式创建 observe_memory 任务（历史回填）。"""
    with store._lock:
        clauses = ["m.role = 'user'"]
        params: list = []
        if conversation_id:
            clauses.append("m.conversation_id = ?")
            params.append(conversation_id)
        rows = store.conn.execute(
            f"""
            SELECT m.id AS message_id, t.id AS turn_id
            FROM messages m
            LEFT JOIN turns t ON t.user_message_id = m.id
            WHERE {' AND '.join(clauses)}
            ORDER BY m.conversation_id, m.seq
            """,
            params,
        ).fetchall()
        count = 0
        now = store.conn.execute("SELECT datetime('now')").fetchone()[0]
        for row in rows:
            exists = store.conn.execute(
                """
                SELECT 1 FROM derivation_outbox
                WHERE kind = 'observe_memory' AND source_message_id = ?
                  AND status IN ('pending', 'running', 'blocked')
                LIMIT 1
                """,
                (row["message_id"],),
            ).fetchone()
            if exists:
                continue
            rev_row = store.conn.execute(
                """
                SELECT COALESCE(MAX(source_revision), 0) + 1
                FROM derivation_outbox
                WHERE kind = 'observe_memory' AND source_message_id = ?
                """,
                (row["message_id"],),
            ).fetchone()
            revision = int(rev_row[0])
            store.conn.execute(
                """
                INSERT INTO derivation_outbox(
                    kind, source_message_id, source_revision, turn_id,
                    status, attempts, next_run_at, created_at, updated_at
                ) VALUES ('observe_memory', ?, ?, ?, 'pending', 0, ?, ?, ?)
                """,
                (row["message_id"], revision, row["turn_id"], now, now, now),
            )
            count += 1
        store.conn.commit()
        return count
