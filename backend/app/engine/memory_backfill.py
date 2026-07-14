"""为已保留用户消息回填 `observe_memory` outbox 任务（历史记忆观察）。

幂等：已有 pending/running/blocked 的 observe_memory 任务不会重复入队。

可执行：
  python -m app.engine.memory_backfill
  python -m app.engine.memory_backfill --conversation-id <cid>
"""

from __future__ import annotations

import argparse
import json

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


def main() -> None:
    from app.config import get_settings

    parser = argparse.ArgumentParser(
        description="为已保留用户消息回填 observe_memory 派生任务"
    )
    parser.add_argument(
        "--conversation-id",
        type=str,
        default=None,
        help="仅处理指定会话（默认全部保留会话）",
    )
    args = parser.parse_args()

    settings = get_settings()
    conversations_dir = settings.kb_path / ".kb" / "conversations"
    store = ConversationStore(conversations_dir)
    enqueued = enqueue_observe_for_retained_messages(
        store, conversation_id=args.conversation_id
    )
    print(
        json.dumps(
            {"enqueued": enqueued, "conversation_id": args.conversation_id},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
