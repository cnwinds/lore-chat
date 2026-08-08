from app.engine.memory_backfill import enqueue_observe_for_retained_messages
from app.engine.conversations import ConversationStore


def test_backfill_enqueues_session_observe(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    cid = store.create()
    store.begin_turn(cid, "我偏好茶", "c1", observation_allowed=True)
    n = enqueue_observe_for_retained_messages(store, conversation_id=cid)
    assert n == 1
    pending = [
        j
        for j in store.list_outbox(kind="session_observe_memory")
        if j["status"] == "pending"
    ]
    assert len(pending) == 1
    assert pending[0]["source_message_id"] == f"conv:{cid}"
