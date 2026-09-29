from app.engine.conversations import ConversationStore
from app.engine.derivation_worker import DerivationWorker
from app.index.conversation_index import ConversationIndex
from app.index.revision import IndexRevision
from tests.helpers import conv_fts_hits, make_search_index


def _fts(tmp_path):
    si = make_search_index(tmp_path)
    return ConversationIndex(si), si


def test_delete_clears_conversation_index(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    fts, si = _fts(tmp_path)
    cid = store.create()
    turn = store.begin_turn(cid, "secret phrase", "c1", observation_allowed=False)
    store.finalize_turn(
        cid,
        turn_id=turn["turn_id"],
        assistant={"text": "ok", "timeline": [], "sources": [], "status": "complete"},
    )
    worker = DerivationWorker(store, fts, chunk_chars=1000, overlap=150)
    worker.drain(10)
    assert conv_fts_hits(si, "secret")

    store.delete(cid, conversation_index=fts)
    assert cid not in fts.conversation_ids()
    assert conv_fts_hits(si, "secret") == []


def test_delete_bumps_revision_when_configured(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    fts, _si = _fts(tmp_path)
    rev = IndexRevision(tmp_path / "rev.txt")
    cid = store.create()
    store.delete(cid, conversation_index=fts, index_revision=rev)
    assert rev.get() == 1
