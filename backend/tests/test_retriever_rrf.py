from app.engine.retriever import Retriever, SearchPage
from app.index.conversation_fts import ConversationFTS
from app.index.conversation_vector import ConversationVector
from app.index.fulltext import FullTextIndex
from app.index.indexer import Indexer
from app.index.message_chunk import MessageChunk
from app.index.revision import IndexRevision
from app.index.vector import VectorIndex
from app.models.llm import FakeLLMClient


def _setup(tmp_path, llm=None):
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    cfts = ConversationFTS(tmp_path / "conversation_fts.db")
    cvec = ConversationVector(tmp_path / "conv_vec")
    rev = IndexRevision(tmp_path / "revision.txt")
    llm = llm or FakeLLMClient(chat_responses=[], embed_dim=8)
    idx = Indexer(vi, fi, llm)
    idx.reindex_doc("技术/漫剧.md", "介绍漫剧工具的使用方法")
    retr = Retriever(
        vi,
        fi,
        llm,
        conversation_fts=cfts,
        conversation_vector=cvec,
        index_revision=rev,
    )
    return retr, cfts, cvec, rev, llm


def test_rrf_merges_four_lanes(tmp_path):
    retr, cfts, cvec, rev, llm = _setup(tmp_path)
    cfts.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="user",
        ts="2026-07-14T10:00:00",
        conversation_title="测试会话",
        chunks=[MessageChunk(0, 0, 4, "漫剧工具")],
    )
    cvec.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="user",
        ts="2026-07-14T10:00:00",
        conversation_title="测试会话",
        chunks=[MessageChunk(0, 0, 4, "漫剧工具")],
        embeddings=llm.embed(["漫剧工具"]),
    )

    page = retr.search("漫剧工具", k=5)

    assert isinstance(page, SearchPage)
    assert page.index_revision >= 0
    sources = {(h.doc_id, h.message_id) for h in page.hits}
    assert ("技术/漫剧.md", None) in sources
    assert any(h.message_id == "m1" for h in page.hits)


def test_cursor_expires_on_revision_bump(tmp_path):
    retr, _cfts, _cvec, rev, _llm = _setup(tmp_path)
    page1 = retr.search("q", k=1)
    assert page1.next_cursor is None or page1.hits
    rev.bump()
    page2 = retr.search("q", k=1, cursor=page1.next_cursor or _make_dummy_cursor(page1))
    if page1.next_cursor:
        assert page2.cursor_expired
    else:
        # force a cursor with stale rev
        from app.engine.retriever import _make_cursor

        stale = _make_cursor("q", {"scope": "all", "conversation_id": None}, 0, 0)
        page2 = retr.search("q", k=1, cursor=stale)
        assert page2.cursor_expired


def _make_dummy_cursor(page1):
    from app.engine.retriever import _make_cursor

    return _make_cursor("q", {"scope": "all", "conversation_id": None}, page1.index_revision, 0)


def test_vector_lane_failure_does_not_break_fts(tmp_path):
    class BrokenEmbedLLM(FakeLLMClient):
        def embed(self, texts):
            raise RuntimeError("embed unavailable")

    retr, cfts, _cvec, _rev, _llm = _setup(tmp_path, llm=BrokenEmbedLLM(embed_dim=8))
    cfts.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="user",
        ts="t",
        conversation_title="",
        chunks=[MessageChunk(0, 0, 4, "漫剧工具")],
    )

    page = retr.search("漫剧", k=5, scope="conversations")

    assert page.hits
    assert page.hits[0].message_id == "m1"
