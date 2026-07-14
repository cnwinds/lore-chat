from app.index.conversation_vector import ConversationVector
from app.index.message_chunk import MessageChunk


def test_upsert_and_query_by_embedding(tmp_path):
    idx = ConversationVector(tmp_path / "vec")
    chunks = [MessageChunk(index=0, text="漫剧剪辑工具", start_char=0, end_char=6)]
    idx.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="user",
        ts="t",
        conversation_title="t",
        chunks=chunks,
        embeddings=[[0.2] * 8],
    )
    hits = idx.query([0.2] * 8, k=5)
    assert len(hits) >= 1
    assert hits[0].message_id == "m1"
    assert hits[0].conversation_id == "c1"
    assert hits[0].chunk_id.startswith("conv:c1:msg:m1:chunk:")


def test_upsert_replaces_same_message(tmp_path):
    idx = ConversationVector(tmp_path / "vec")
    c1 = [MessageChunk(index=0, text="旧内容AAA", start_char=0, end_char=5)]
    c2 = [MessageChunk(index=0, text="新内容BBB", start_char=0, end_char=5)]
    idx.upsert_message_chunks(
        conversation_id="c1", message_id="m1", role="user", ts="t",
        conversation_title="", chunks=c1, embeddings=[[0.1] * 8],
    )
    idx.upsert_message_chunks(
        conversation_id="c1", message_id="m1", role="user", ts="t",
        conversation_title="", chunks=c2, embeddings=[[0.9] * 8],
    )
    assert idx.count_for_message("c1", "m1") == 1


def test_delete_conversation(tmp_path):
    idx = ConversationVector(tmp_path / "vec")
    idx.upsert_message_chunks(
        conversation_id="c1", message_id="m1", role="user", ts="t",
        conversation_title="", chunks=[MessageChunk(0, 0, 14, "hello world xx")],
        embeddings=[[0.3] * 8],
    )
    idx.delete_conversation("c1")
    assert idx.query([0.3] * 8, k=5) == []
