# backend/tests/test_retriever_provenance.py
from app.engine.provenance import conversation_ids_from_meta, merge_adjacent_conversation_hits, group_provenance
from app.index.types import Hit


def test_conversation_ids_from_meta_list_and_legacy():
    assert conversation_ids_from_meta({"conversation_ids": ["a", "b"]}) == ["a", "b"]
    assert conversation_ids_from_meta({"conversation_id": "legacy"}) == ["legacy"]


def test_merge_adjacent_chunks_same_message():
    hits = [
        Hit("a", "hel", 1.0, "conv:c1", message_id="m1", start_char=0, end_char=3),
        Hit("b", "lo", 0.9, "conv:c1", message_id="m1", start_char=3, end_char=5),
        Hit("c", "x", 0.8, "conv:c2", message_id="m2", start_char=0, end_char=1),
    ]
    merged = merge_adjacent_conversation_hits(hits)
    assert len(merged) == 2
    assert merged[0].chunk == "hello"
    assert merged[0].end_char == 5


def test_group_provenance_links_summary_and_message():
    kb = Hit("d1", "摘要段", 1.0, "娱乐/盘点.md")
    msg = Hit("c1", "原文", 0.9, "conv:abc", message_id="m1", start_char=0, end_char=2)
    doc_ids = {"娱乐/盘点.md": ["abc"]}
    groups = group_provenance([kb, msg], doc_conversation_ids=doc_ids)
    assert len(groups) == 1
    assert groups[0]["group_key"] == "conversation:abc"
    assert groups[0]["nav_preference"] == "summary"
    assert len(groups[0]["hits"]) == 2


def test_conv_vector_lane_respects_min_score(tmp_path, monkeypatch):
    from app.engine.retriever import Retriever
    from app.index.conversation_vector import ConversationVector, ConversationVectorHit
    from app.index.fulltext import FullTextIndex
    from app.index.message_chunk import MessageChunk
    from app.index.revision import IndexRevision
    from app.index.vector import VectorIndex
    from app.models.llm import FakeLLMClient

    llm = FakeLLMClient(embed_dim=8)
    retr = Retriever(
        VectorIndex(tmp_path / "vec"),
        FullTextIndex(tmp_path / "fts.db"),
        llm,
        min_score=0.45,
        conversation_vector=ConversationVector(tmp_path / "vec"),
        index_revision=IndexRevision(tmp_path / "rev.txt"),
    )
    cv = retr.conversation_vector
    assert cv is not None
    cv.upsert_message_chunks(
        conversation_id="c1",
        message_id="low",
        role="user",
        ts="t",
        conversation_title="",
        chunks=[MessageChunk(0, 0, 4, "低分命中")],
        embeddings=[[0.01] * 8],
    )
    cv.upsert_message_chunks(
        conversation_id="c1",
        message_id="high",
        role="user",
        ts="t",
        conversation_title="",
        chunks=[MessageChunk(0, 0, 4, "高分命中")],
        embeddings=[[1.0] * 8],
    )

    def fake_query(embedding, k=5, *, conversation_id=None, exclude_conversation_id=None):
        return [
            ConversationVectorHit("a", "c1", "low", "user", 0, 4, "低分", 0.1),
            ConversationVectorHit("b", "c1", "high", "user", 0, 4, "高分", 0.95),
        ]

    monkeypatch.setattr(cv, "query", fake_query)
    ids, hit_map = retr._conv_vector_lane(
        "q", 5, conversation_id="c1", exclude_conversation_id=None
    )
    assert ids == ["b"]
    assert "a" not in hit_map
