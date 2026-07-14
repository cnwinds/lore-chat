from app.engine.conversations import ConversationStore
from app.engine.derivation_worker import DerivationWorker
from app.index.conversation_fts import ConversationFTS
from app.index.conversation_vector import ConversationVector
from app.models.llm import FakeLLMClient


def _worker(tmp_path, store, fts, *, with_vector=False):
    vec = ConversationVector(tmp_path / "conv_vec") if with_vector else None
    llm = FakeLLMClient(embed_dim=8) if with_vector else None
    return DerivationWorker(store, fts, conversation_vector=vec, llm=llm, chunk_chars=1000, overlap=150), vec, llm


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
    worker, _, _ = _worker(tmp_path, store, fts)
    n = worker.drain(max_jobs=10)
    assert n >= 2
    hits = fts.query("剪映", k=5)
    assert hits
    assert hits[0].conversation_id == cid


def test_worker_indexes_vector(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    fts = ConversationFTS(tmp_path / "conv_fts.db")
    cid = store.create()
    turn = store.begin_turn(cid, user_text="漫剧剪辑工具有哪些", client_message_id="c1", observation_allowed=False)
    store.finalize_turn(
        cid,
        turn_id=turn["turn_id"],
        assistant={"text": "剪映和小云雀", "timeline": [{"type": "text", "content": "剪映和小云雀"}], "sources": [], "status": "complete"},
    )
    worker, vec, llm = _worker(tmp_path, store, fts, with_vector=True)
    assert llm is not None and vec is not None
    n = worker.drain(max_jobs=20)
    assert n >= 4
    hits = vec.query(llm.embed(["漫剧"])[0], k=5)
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
    worker, _, _ = _worker(tmp_path, store, fts)
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
    worker, _, _ = _worker(tmp_path, store, fts)
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
