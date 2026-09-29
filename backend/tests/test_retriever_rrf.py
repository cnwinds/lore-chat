from app.engine.retriever import Retriever, SearchPage
from app.index.conversation_index import ConversationIndex
from app.index.indexer import Indexer
from app.index.message_chunk import MessageChunk
from app.index.revision import IndexRevision
from app.models.llm import FakeLLMClient
from tests.helpers import drain_embeddings, make_search_index


def _setup(tmp_path, llm=None):
    rev = IndexRevision(tmp_path / "rev.txt")
    llm = llm or FakeLLMClient(chat_responses=[], embed_dim=8)
    si = make_search_index(tmp_path, llm)
    ci = ConversationIndex(si)
    idx = Indexer(si)
    idx.reindex_doc("技术/漫剧.md", "介绍漫剧工具的使用方法")
    drain_embeddings(si)
    retr = Retriever(si, llm, index_revision=rev)
    return retr, ci, rev, llm


def test_rrf_merges_four_lanes(tmp_path):
    retr, ci, rev, llm = _setup(tmp_path)
    ci.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="user",
        ts="2026-07-14T10:00:00",
        conversation_title="测试会话",
        chunks=[MessageChunk(0, 0, 4, "漫剧工具")],
    )
    drain_embeddings(retr.search_index)

    page = retr.search("漫剧工具", k=5)

    assert isinstance(page, SearchPage)
    assert page.index_revision >= 0
    sources = {(h.doc_id, h.message_id) for h in page.hits}
    assert ("技术/漫剧.md", None) in sources
    assert any(h.message_id == "m1" for h in page.hits)


def test_cursor_expires_on_revision_bump(tmp_path):
    retr, _ci, rev, _llm = _setup(tmp_path)
    page1 = retr.search("q", k=1)
    assert page1.next_cursor is None or page1.hits
    rev.bump()
    page2 = retr.search("q", k=1, cursor=page1.next_cursor or _make_dummy_cursor(page1))
    if page1.next_cursor:
        assert page2.cursor_expired
    else:
        from app.engine.retriever import _make_cursor

        stale = _make_cursor("q", {"scope": "all", "conversation_id": None}, 0, 0)
        page2 = retr.search("q", k=1, cursor=stale)
        assert page2.cursor_expired


def _make_dummy_cursor(page1):
    from app.engine.retriever import _make_cursor

    return _make_cursor("q", {"scope": "all", "conversation_id": None}, page1.index_revision, 0)


def test_vector_lane_failure_does_not_break_fts(tmp_path, monkeypatch):
    llm = FakeLLMClient(embed_dim=8)
    si = make_search_index(tmp_path, llm)
    ci = ConversationIndex(si)
    ci.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="user",
        ts="t",
        conversation_title="",
        chunks=[MessageChunk(0, 0, 4, "漫剧工具")],
    )
    retr = Retriever(si, llm, min_score=0.0)
    orig = si.search

    def broken_search(*args, **kwargs):
        from app.index.partitioned import SearchResult

        if kwargs.get("partitions") == ["conv:main"]:
            return SearchResult(
                hits=[],
                vector_status="unavailable",
                query_terms=(),
                elapsed_ms=0,
                lanes={
                    "conv:fts": orig(*args, **kwargs).lanes.get("conv:fts", [])
                },
                fts_tiers={"conv": "strict"},
            )
        return orig(*args, **kwargs)

    monkeypatch.setattr(si, "search", broken_search)

    page = retr.search("漫剧", k=5, scope="conversations")
    assert page.hits
    assert page.hits[0].message_id == "m1"
