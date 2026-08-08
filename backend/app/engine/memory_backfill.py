"""为 dirty 会话回填 `session_observe_memory`（历史记忆观察）。

幂等：已有 pending/running 的 session 任务不会重复入队。

用法：
  python -m app.engine.memory_backfill
  python -m app.engine.memory_backfill --conversation-id <cid>
"""

from __future__ import annotations

import argparse

from app.config import Settings
from app.deps import build_container
from app.engine.conversations import ConversationStore


def enqueue_session_observe_for_conversations(
    store: ConversationStore,
    *,
    conversation_id: str | None = None,
    mark_dirty: bool = True,
) -> int:
    """为指定或全部会话标记 dirty 并入队会话级观察。"""
    with store._lock:
        if conversation_id:
            cids = [conversation_id]
        else:
            rows = store.conn.execute("SELECT id FROM conversations").fetchall()
            cids = [r["id"] for r in rows]
        n = 0
        for cid in cids:
            if mark_dirty:
                store._mark_memory_dirty_unlocked(cid)
            if store._enqueue_session_observe_unlocked(cid):
                n += 1
        store.conn.commit()
        return n


def enqueue_observe_for_retained_messages(
    store: ConversationStore,
    *,
    conversation_id: str | None = None,
) -> int:
    """兼容旧名 → 会话级入队。"""
    return enqueue_session_observe_for_conversations(
        store, conversation_id=conversation_id, mark_dirty=True
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="回填会话级记忆观察任务")
    parser.add_argument("--conversation-id", default=None)
    args = parser.parse_args()
    container = build_container(Settings())
    n = enqueue_session_observe_for_conversations(
        container.conversations, conversation_id=args.conversation_id
    )
    print(f"enqueued session_observe_memory jobs: {n}")


if __name__ == "__main__":
    main()
