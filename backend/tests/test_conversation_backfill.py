import json

from app.engine.conversation_backfill import (
    backfill_conversation_fts,
    backfill_conversation_vectors,
)
from app.engine.conversations import ConversationStore
from app.index.conversation_fts import ConversationFTS
from app.index.conversation_vector import ConversationVector
from app.models.llm import FakeLLMClient


def _store(tmp_path):
    return ConversationStore(tmp_path / ".kb" / "conversations")


def _fts(tmp_path):
    return ConversationFTS(tmp_path / ".kb" / "index" / "conversation_fts.db")


def _create_turn(store, cid, *, user_text, assistant_text, client_message_id="c1"):
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
            "text": assistant_text,
            "timeline": [{"type": "text", "content": assistant_text}],
            "sources": [],
            "status": "complete",
        },
    )
    return turn


def test_backfill_indexes_all_retained_messages_and_is_idempotent(tmp_path):
    store = _store(tmp_path)
    fts = _fts(tmp_path)
    cid = store.create()
    _create_turn(
        store,
        cid,
        user_text="漫剧剪辑工具有哪些",
        assistant_text="剪映和小云雀",
    )

    # outbox 从未被 worker 消费，FTS 应为空。
    assert fts.query("漫剧") == []
    assert fts.query("剪映") == []

    stats1 = backfill_conversation_fts(store, fts, deletion_ledger_path=None)
    assert stats1["indexed"] >= 2
    assert fts.query("漫剧")
    assert fts.query("剪映")

    stats2 = backfill_conversation_fts(store, fts, deletion_ledger_path=None)
    assert stats2["indexed"] == 0
    assert fts.query("漫剧")
    assert fts.query("剪映")


def test_backfill_skips_cids_present_in_deletion_ledger(tmp_path):
    store = _store(tmp_path)
    fts = _fts(tmp_path)
    cid = store.create()
    _create_turn(
        store,
        cid,
        user_text="将被判定删除但尚未清理",
        assistant_text="回复内容",
    )

    ledger_path = tmp_path / ".kb" / "migrations" / "conversation-deletions.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(
        json.dumps(
            {
                "conversation_id": cid,
                "deletion_id": "d1",
                "deleted_at": "2026-07-14T00:00:00",
                "options": {"delete_summary": True},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    stats = backfill_conversation_fts(store, fts, deletion_ledger_path=ledger_path)
    assert stats["skipped_deleted"] == 1
    assert stats["scanned"] == 0
    assert fts.query("判定删除") == []


def test_backfill_via_conversation_store_delete_ledger_is_respected(tmp_path):
    store = _store(tmp_path)
    fts = _fts(tmp_path)
    cid_keep = store.create()
    cid_delete = store.create()
    _create_turn(
        store,
        cid_keep,
        user_text="保留的会话漫剧内容",
        assistant_text="保留回复",
        client_message_id="keep-1",
    )
    _create_turn(
        store,
        cid_delete,
        user_text="删除的会话小云雀内容",
        assistant_text="删除回复",
        client_message_id="del-1",
    )

    ledger_path = tmp_path / ".kb" / "migrations" / "conversation-deletions.jsonl"
    store.delete(cid_delete, conversation_fts=fts, ledger_path=ledger_path)

    stats = backfill_conversation_fts(store, fts, deletion_ledger_path=ledger_path)
    assert stats["indexed"] >= 2
    assert fts.query("漫剧")
    assert fts.query("小云雀") == []


def test_backfill_leaves_already_covered_messages_untouched(tmp_path):
    store = _store(tmp_path)
    fts = _fts(tmp_path)
    cid = store.create()
    turn = _create_turn(
        store,
        cid,
        user_text="覆盖检查用例",
        assistant_text="覆盖检查回复",
    )
    user_message_id = turn["user_message"]["id"]

    stats1 = backfill_conversation_fts(store, fts, deletion_ledger_path=None)
    ranges_after_first = fts.covered_ranges(cid, user_message_id)
    assert ranges_after_first

    stats2 = backfill_conversation_fts(store, fts, deletion_ledger_path=None)
    assert stats2["indexed"] == 0
    assert fts.covered_ranges(cid, user_message_id) == ranges_after_first


def test_backfill_vectors_indexes_messages_and_is_idempotent(tmp_path):
    store = _store(tmp_path)
    vec = ConversationVector(tmp_path / ".kb" / "index" / "vec")
    llm = FakeLLMClient(embed_dim=8)
    cid = store.create()
    _create_turn(
        store,
        cid,
        user_text="漫剧剪辑工具有哪些",
        assistant_text="剪映和小云雀",
    )

    stats1 = backfill_conversation_vectors(store, vec, llm, deletion_ledger_path=None)
    assert stats1["indexed"] >= 2
    hits = vec.query(llm.embed(["漫剧"])[0], k=5)
    assert hits

    stats2 = backfill_conversation_vectors(store, vec, llm, deletion_ledger_path=None)
    assert stats2["indexed"] == 0
    assert vec.query(llm.embed(["剪映"])[0], k=5)


def test_backfill_vectors_resumes_from_checkpoint(tmp_path):
    store = _store(tmp_path)
    vec = ConversationVector(tmp_path / ".kb" / "index" / "vec")
    llm = FakeLLMClient(embed_dim=8)
    cid1 = store.create()
    cid2 = store.create()
    _create_turn(
        store,
        cid1,
        user_text="第一条漫剧消息",
        assistant_text="第一条回复",
        client_message_id="a",
    )
    _create_turn(
        store,
        cid2,
        user_text="第二条小云雀消息",
        assistant_text="第二条回复",
        client_message_id="b",
    )

    all_ids: list[str] = []
    for summary in store.list_all():
        conv = store.get(summary["id"])
        for msg in conv.get("messages", []):
            if msg.get("role") in ("user", "assistant"):
                all_ids.append(msg["id"])
    all_ids.sort()
    assert len(all_ids) >= 4
    resume_after = all_ids[1]

    checkpoint = tmp_path / "vector.checkpoint.json"
    checkpoint.write_text(
        json.dumps({"last_message_id": resume_after, "indexed": 2}, ensure_ascii=False),
        encoding="utf-8",
    )

    stats = backfill_conversation_vectors(
        store,
        vec,
        llm,
        deletion_ledger_path=None,
        checkpoint_path=checkpoint,
        batch_size=1,
    )
    assert stats["indexed"] == len(all_ids) - 2
    assert vec.query(llm.embed(["小云雀"])[0], k=5)
    saved = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert saved["indexed"] == len(all_ids)
