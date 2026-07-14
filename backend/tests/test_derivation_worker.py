from app.engine.conversations import ConversationStore
from app.engine.derivation_worker import DerivationWorker
from app.index.conversation_fts import ConversationFTS


def test_worker_indexes_user_and_assistant_messages(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    fts = ConversationFTS(tmp_path / "conv_fts.db")
    cid = store.create()
    turn = store.begin_turn(cid, user_text="漫剧剪辑工具有哪些", client_message_id="c1", observation_allowed=False)
    store.finalize_turn(
        cid,
        turn_id=turn["turn_id"],
        assistant={"text": "剪映和小云雀", "timeline": [{"type": "text", "content": "剪映和小云雀"}], "sources": [], "status": "complete"},
    )
    worker = DerivationWorker(store, fts, chunk_chars=1000, overlap=150)
    n = worker.drain(max_jobs=10)
    assert n >= 2
    hits = fts.query("剪映", k=5)
    assert hits
    assert hits[0].conversation_id == cid


def test_worker_masks_secrets_before_indexing(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    fts = ConversationFTS(tmp_path / "conv_fts.db")
    cid = store.create()
    turn = store.begin_turn(
        cid,
        user_text="我的密钥是 sk-ABCDEFGHIJKLMNOPQRSTUV1234567890",
        client_message_id="c1",
        observation_allowed=False,
    )
    worker = DerivationWorker(store, fts, chunk_chars=1000, overlap=150)
    n = worker.drain(max_jobs=10)
    assert n >= 1
    hits = fts.query("ABCDEFGHIJKLMNOPQRSTUV", k=5)
    assert hits == []
    hits2 = fts.query("密钥", k=5)
    assert hits2
    assert "sk-ABCDEFGHIJKLMNOPQRSTUV1234567890" not in hits2[0].text
    assert turn is not None


def test_drain_returns_zero_when_no_jobs(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    fts = ConversationFTS(tmp_path / "conv_fts.db")
    worker = DerivationWorker(store, fts, chunk_chars=1000, overlap=150)
    assert worker.drain(max_jobs=10) == 0


def test_fail_outbox_retries_then_dies(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    cid = store.create()
    turn = store.begin_turn(cid, user_text="hi", client_message_id="c1", observation_allowed=False)
    jobs = store.claim_outbox(kind="index_fts", limit=10, lease_seconds=60)
    assert len(jobs) == 1
    job_id = jobs[0]["id"]
    for _ in range(5):
        store.fail_outbox(job_id, "boom", backoff=0.0)
    row = store.conn.execute(
        "SELECT status, attempts FROM derivation_outbox WHERE id = ?", (job_id,)
    ).fetchone()
    assert row["status"] == "dead"
    assert row["attempts"] == 5
    assert turn is not None


def test_claim_outbox_does_not_reclaim_active_lease(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    cid = store.create()
    store.begin_turn(cid, user_text="hi", client_message_id="c1", observation_allowed=False)
    first = store.claim_outbox(kind="index_fts", limit=10, lease_seconds=60)
    assert len(first) == 1
    second = store.claim_outbox(kind="index_fts", limit=10, lease_seconds=60)
    assert second == []
