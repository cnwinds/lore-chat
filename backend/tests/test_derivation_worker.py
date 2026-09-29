from app.engine.conversations import ConversationStore
from app.engine.derivation_worker import DerivationWorker
from app.index.conversation_index import ConversationIndex
from tests.helpers import conv_fts_hits, make_search_index


def _worker(tmp_path, *, with_vector_job: bool = False):
    store = ConversationStore(tmp_path / "conversations")
    si = make_search_index(tmp_path)
    ci = ConversationIndex(si)
    worker = DerivationWorker(store, ci, chunk_chars=1000, overlap=150)
    return worker, store, ci, si


def test_fts_job_indexes_message(tmp_path):
    worker, store, ci, si = _worker(tmp_path)
    cid = store.create()
    turn = store.begin_turn(cid, "hello world", "c1", observation_allowed=False)
    store.finalize_turn(
        cid,
        turn_id=turn["turn_id"],
        assistant={"text": "ok", "timeline": [], "sources": [], "status": "complete"},
    )
    jobs = worker.claim_jobs(kind="index_fts", limit=1)
    assert len(jobs) == 1
    worker.process_fts_job(jobs[0])
    assert conv_fts_hits(si, "hello")


def test_vector_job_same_as_fts(tmp_path):
    worker, store, ci, si = _worker(tmp_path)
    cid = store.create()
    turn = store.begin_turn(cid, "vector path", "c1", observation_allowed=False)
    store.finalize_turn(
        cid,
        turn_id=turn["turn_id"],
        assistant={"text": "ok", "timeline": [], "sources": [], "status": "complete"},
    )
    msg_id = store.conn.execute(
        "SELECT id FROM messages WHERE conversation_id=? LIMIT 1", (cid,)
    ).fetchone()[0]
    # finalize 已入队 index_fts；单独测遗留 index_vector 任务
    store.conn.execute(
        """
        INSERT INTO derivation_outbox(
            kind, source_message_id, source_revision, turn_id,
            status, attempts, next_run_at, created_at, updated_at
        ) VALUES ('index_vector', ?, 1, ?, 'pending', 0, datetime('now'), datetime('now'), datetime('now'))
        """,
        (msg_id, turn["turn_id"]),
    )
    store.conn.commit()
    jobs = worker.claim_jobs(kind="index_vector", limit=1)
    worker.process_vector_job(jobs[0])
    assert conv_fts_hits(si, "vector")
