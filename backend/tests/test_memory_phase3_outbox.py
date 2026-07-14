"""Phase 3: observe_memory outbox enqueue and finalize gating."""

from app.engine.conversations import ConversationStore


def _store(tmp_path):
    return ConversationStore(tmp_path / "knowledge" / ".kb" / "conversations")


def test_begin_turn_enqueues_blocked_observe_memory(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    turn = store.begin_turn(cid, "我喜欢简洁", "c1", observation_allowed=True)
    jobs = store.list_outbox(kind="observe_memory", message_id=turn["user_message"]["id"])
    assert len(jobs) == 1
    assert jobs[0]["status"] == "blocked"


def test_finalize_cancels_observe_when_not_allowed(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    turn = store.begin_turn(cid, "hi", "c1", observation_allowed=False)
    store.finalize_turn(
        cid,
        turn["turn_id"],
        assistant={"text": "ok", "timeline": [], "sources": [], "status": "complete"},
    )
    jobs = store.list_outbox(kind="observe_memory")
    assert jobs[0]["status"] == "cancelled"


def test_finalize_activates_observe_when_allowed(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    turn = store.begin_turn(cid, "我喜欢茶", "c1", observation_allowed=True)
    store.finalize_turn(
        cid,
        turn["turn_id"],
        assistant={"text": "好", "timeline": [], "sources": [], "status": "complete"},
    )
    jobs = store.list_outbox(kind="observe_memory")
    assert jobs[0]["status"] == "pending"


def test_claim_skips_blocked_observe_before_finalize(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    turn = store.begin_turn(cid, "我喜欢茶", "c1", observation_allowed=True)
    claimed = store.claim_outbox(kind="observe_memory", limit=5)
    assert claimed == []
    store.finalize_turn(
        cid,
        turn["turn_id"],
        assistant={"text": "好", "timeline": [], "sources": [], "status": "complete"},
    )
    claimed = store.claim_outbox(kind="observe_memory", limit=5)
    assert len(claimed) == 1
