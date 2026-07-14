import json

import pytest

from app.engine.conversations import ConversationStore
from app.engine.derivation_worker import DerivationWorker
from app.index.conversation_fts import ConversationFTS


def _store(tmp_path):
    return ConversationStore(tmp_path / ".kb" / "conversations")


def _fts(tmp_path):
    return ConversationFTS(tmp_path / ".kb" / "index" / "conversation_fts.db")


def _create_turn(store, cid, *, user_text="漫剧剪辑工具有哪些", client_message_id="c1"):
    turn = store.begin_turn(
        cid,
        user_text=user_text,
        client_message_id=client_message_id,
        observation_allowed=False,
    )
    store.finalize_turn(
        cid,
        turn_id=turn["turn_id"],
        assistant={
            "text": "剪映和小云雀",
            "timeline": [{"type": "text", "content": "剪映和小云雀"}],
            "sources": [],
            "status": "complete",
        },
    )
    return turn


def test_delete_conversation_removes_fts_and_writes_ledger(tmp_path):
    store = _store(tmp_path)
    fts = _fts(tmp_path)
    cid = store.create()
    _create_turn(store, cid)

    worker = DerivationWorker(store, fts, chunk_chars=1000, overlap=150)
    assert worker.drain(max_jobs=10) >= 2
    assert fts.query("漫剧")

    store.delete(cid, conversation_fts=fts)

    assert fts.query("漫剧") == []
    ledger_path = tmp_path / ".kb" / "migrations" / "conversation-deletions.jsonl"
    content = ledger_path.read_text(encoding="utf-8")
    assert cid in content
    entry = json.loads(content.strip().splitlines()[-1])
    assert entry["conversation_id"] == cid
    assert entry["deletion_id"]
    assert entry["options"]["delete_summary"] is True

    with pytest.raises(KeyError):
        store.get(cid)


def test_delete_cancels_pending_outbox_jobs(tmp_path):
    store = _store(tmp_path)
    cid = store.create()
    _create_turn(store, cid, client_message_id="c-pending")
    # Outbox jobs from begin_turn/finalize_turn are never drained here.

    store.delete(cid)

    jobs = store.claim_outbox(kind="index_fts", limit=50)
    assert jobs == []


def test_delete_calls_indexer_remove_conversation_for_legacy_fts(tmp_path):
    calls = []

    class FakeIndexer:
        def remove_conversation(self, cid):
            calls.append(cid)

    store = _store(tmp_path)
    cid = store.create()
    _create_turn(store, cid, client_message_id="c-legacy")

    store.delete(cid, indexer=FakeIndexer())

    assert calls == [cid]


def test_delete_missing_conversation_raises_keyerror(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(KeyError):
        store.delete("does-not-exist")


def test_delete_appends_ledger_entry_per_conversation(tmp_path):
    store = _store(tmp_path)
    cid1 = store.create()
    cid2 = store.create()
    _create_turn(store, cid1, client_message_id="c-a")
    _create_turn(store, cid2, client_message_id="c-b")

    store.delete(cid1)
    store.delete(cid2)

    ledger_path = tmp_path / ".kb" / "migrations" / "conversation-deletions.jsonl"
    lines = [
        line for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert len(lines) == 2
    cids_in_ledger = {json.loads(line)["conversation_id"] for line in lines}
    assert cids_in_ledger == {cid1, cid2}
