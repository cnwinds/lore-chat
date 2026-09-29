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
    import json

    json.dumps(groups, ensure_ascii=False)
    assert isinstance(groups[0]["hits"][0], dict)
    assert groups[0]["hits"][0]["source"] == "娱乐/盘点.md"
    assert groups[0]["hits"][1]["message_id"] == "m1"


def test_conv_vector_lane_respects_min_score(tmp_path, monkeypatch):
    from app.engine.retriever import Retriever
    from app.index.partitioned import SearchHit, SearchResult
    from app.index.revision import IndexRevision
    from app.models.llm import FakeLLMClient
    from tests.helpers import make_search_index

    llm = FakeLLMClient(embed_dim=8)
    si = make_search_index(tmp_path, llm)
    retr = Retriever(
        si,
        llm,
        min_score=0.45,
        index_revision=IndexRevision(tmp_path / "rev.txt"),
    )

    low = SearchHit(
        partition="conv:main",
        item_id="a",
        text="低分",
        meta={
            "conversation_id": "c1",
            "message_id": "low",
            "role": "user",
            "ts": "t",
            "start_char": 0,
            "end_char": 4,
            "chunk_index": 0,
            "conversation_title": "",
            "offset_version": "unicode-codepoint-v1",
        },
        score=0.1,
        bm25=None,
        matched_terms=(),
        rare_terms=(),
        vector_score=0.1,
    )
    high = SearchHit(
        partition="conv:main",
        item_id="b",
        text="高分",
        meta={
            "conversation_id": "c1",
            "message_id": "high",
            "role": "user",
            "ts": "t",
            "start_char": 0,
            "end_char": 4,
            "chunk_index": 0,
            "conversation_title": "",
            "offset_version": "unicode-codepoint-v1",
        },
        score=0.95,
        bm25=None,
        matched_terms=(),
        rare_terms=(),
        vector_score=0.95,
    )

    def fake_search(*_a, **_k):
        return SearchResult(
            hits=[high],
            vector_status="ok",
            query_terms=(),
            elapsed_ms=0,
            lanes={"conv:vec": [low, high]},
            fts_tiers={},
        )

    monkeypatch.setattr(si, "search", fake_search)
    _fts_out, (ids, hit_map, _meta) = retr._conv_lanes(
        "q",
        5,
        vector_text="q",
        conversation_id="c1",
        exclude_conversation_id=None,
    )
    assert ids == ["b"]
    assert "a" not in hit_map
