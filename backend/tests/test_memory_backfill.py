from app.engine.conversations import ConversationStore
from app.engine.memory_backfill import enqueue_observe_for_retained_messages


def _store(tmp_path):
    return ConversationStore(tmp_path / "knowledge" / ".kb" / "conversations")


def test_backfill_enqueues_observe_for_retained_messages(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    turn = store.begin_turn(cid, "我偏好茶", "c1", observation_allowed=True)
    store.finalize_turn(
        cid,
        turn["turn_id"],
        assistant={"text": "好", "timeline": [], "sources": [], "status": "complete"},
    )
    for job in store.list_outbox(kind="observe_memory"):
        store.complete_outbox(job["id"])
    n = enqueue_observe_for_retained_messages(store, conversation_id=cid)
    assert n == 1
    pending = [j for j in store.list_outbox(kind="observe_memory") if j["status"] == "pending"]
    assert pending
