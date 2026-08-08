"""会话级记忆：begin_turn 只打 dirty，不再按条 enqueue observe_memory。"""

from app.engine.conversations import ConversationStore


def _store(tmp_path):
    return ConversationStore(tmp_path / "knowledge" / ".kb" / "conversations")


def test_begin_turn_marks_dirty_without_observe_outbox(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    store.begin_turn(cid, "我喜欢简洁", "c1", observation_allowed=True)
    assert store.list_outbox(kind="observe_memory") == []
    row = store.conn.execute(
        "SELECT memory_dirty FROM conversations WHERE id = ?", (cid,)
    ).fetchone()
    assert row["memory_dirty"] == 1


def test_finalize_does_not_create_per_message_observe(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    turn = store.begin_turn(cid, "我喜欢茶", "c1", observation_allowed=True)
    store.finalize_turn(
        cid,
        turn["turn_id"],
        assistant={"text": "好", "timeline": [], "sources": [], "status": "complete"},
    )
    assert store.list_outbox(kind="observe_memory") == []


def test_claim_legacy_observe_returns_empty(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    store.begin_turn(cid, "我喜欢茶", "c1", observation_allowed=True)
    assert store.claim_outbox(kind="observe_memory", limit=5) == []
