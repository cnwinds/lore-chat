from app.engine.conversation_backfill import backfill_conversation_fts
from app.engine.conversations import ConversationStore
from app.index.conversation_index import ConversationIndex
from tests.helpers import conv_fts_hits, make_search_index


def _fts(tmp_path):
    si = make_search_index(tmp_path)
    return ConversationIndex(si), si


def test_backfill_idempotent(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    fts, si = _fts(tmp_path)
    cid = store.create()
    turn = store.begin_turn(cid, "backfill token", "c1", observation_allowed=False)
    store.finalize_turn(
        cid,
        turn_id=turn["turn_id"],
        assistant={"text": "ok", "timeline": [], "sources": [], "status": "complete"},
    )

    stats1 = backfill_conversation_fts(store, fts, deletion_ledger_path=None)
    assert stats1["indexed"] >= 1
    assert conv_fts_hits(si, "backfill")

    stats2 = backfill_conversation_fts(store, fts, deletion_ledger_path=None)
    assert stats2["indexed"] == 0


def test_backfill_skips_deleted_ledger(tmp_path):
    store = ConversationStore(tmp_path / "conversations")
    fts, si = _fts(tmp_path)
    ledger = tmp_path / "deletions.jsonl"
    cid_keep = store.create()
    turn = store.begin_turn(cid_keep, "keep me", "c1", observation_allowed=False)
    store.finalize_turn(
        cid_keep,
        turn_id=turn["turn_id"],
        assistant={"text": "ok", "timeline": [], "sources": [], "status": "complete"},
    )
    cid_delete = store.create()
    turn_del = store.begin_turn(cid_delete, "gone", "c1", observation_allowed=False)
    store.finalize_turn(
        cid_delete,
        turn_id=turn_del["turn_id"],
        assistant={"text": "x", "timeline": [], "sources": [], "status": "complete"},
    )
    ledger.write_text(
        '{"conversation_id": "%s"}\n' % cid_delete,
        encoding="utf-8",
    )

    stats = backfill_conversation_fts(store, fts, deletion_ledger_path=ledger)
    assert stats["skipped_deleted"] >= 1
    assert conv_fts_hits(si, "keep")
