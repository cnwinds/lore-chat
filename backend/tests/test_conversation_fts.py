from app.index.conversation_fts import ConversationFTS
from app.index.message_chunk import MessageChunk


def test_upsert_and_query_by_message(tmp_path):
    fts = ConversationFTS(tmp_path / "fts.db")
    chunks = [
        MessageChunk(0, 0, 5, "你好世界"),
        MessageChunk(1, 5, 10, "漫剧工具"),
    ]
    fts.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="user",
        ts="2026-07-14T10:00:00",
        conversation_title="测试",
        chunks=chunks,
    )
    hits = fts.query("漫剧", k=5)
    assert hits
    assert hits[0].message_id == "m1"
    assert hits[0].conversation_id == "c1"


def test_delete_conversation_removes_all_chunks(tmp_path):
    fts = ConversationFTS(tmp_path / "fts.db")
    fts.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="user",
        ts="t",
        conversation_title="t",
        chunks=[MessageChunk(0, 0, 2, "ab")],
    )
    fts.delete_conversation("c1")
    assert fts.query("ab", k=5) == []
