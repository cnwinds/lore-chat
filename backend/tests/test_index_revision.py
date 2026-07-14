from app.engine.conversations import ConversationStore
from app.index.revision import IndexRevision


def test_index_revision_starts_at_zero_and_bumps(tmp_path):
    rev = IndexRevision(tmp_path / "revision.txt")
    assert rev.get() == 0
    assert rev.bump() == 1
    assert rev.get() == 1
    assert rev.bump() == 2


def test_begin_turn_enqueues_fts_and_vector(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    cid = store.create()
    store.begin_turn(cid, "hi", "cli-1", observation_allowed=False)
    rows = store.conn.execute(
        "SELECT kind FROM derivation_outbox WHERE status='pending' ORDER BY kind"
    ).fetchall()
    kinds = [r[0] for r in rows]
    assert kinds == ["index_fts", "index_vector"]
