from app.engine.retriever import Retriever
from app.index.conversation_fts import ConversationFTS
from app.index.fulltext import FullTextIndex
from app.index.message_chunk import MessageChunk
from app.index.vector import VectorIndex
from app.models.llm import FakeLLMClient


def _setup(tmp_path):
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    cfts = ConversationFTS(tmp_path / "conversation_fts.db")
    llm = FakeLLMClient(chat_responses=[], embed_dim=8)
    return vi, fi, cfts, llm


def test_retriever_includes_conversation_message_hits(tmp_path):
    vi, fi, cfts, llm = _setup(tmp_path)
    cfts.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="user",
        ts="2026-07-14T10:00:00",
        conversation_title="测试会话",
        chunks=[MessageChunk(0, 0, 4, "漫剧工具")],
    )
    retr = Retriever(vi, fi, llm, conversation_fts=cfts)

    hits = retr.search("漫剧", k=5)

    assert hits
    hit = next(h for h in hits if h.message_id == "m1")
    assert hit.source == "conv:c1"
    assert hit.start_char == 0
    assert hit.end_char == 4
    assert hit.offset_version == "unicode-codepoint-v1"


def test_retriever_without_conversation_fts_has_no_message_hits(tmp_path):
    vi, fi, _cfts, llm = _setup(tmp_path)
    retr = Retriever(vi, fi, llm)

    hits = retr.search("漫剧", k=5)

    assert hits == []


def test_retriever_merges_kb_and_conversation_hits_sorted_by_score(tmp_path):
    from app.index.indexer import Indexer

    vi, fi, cfts, llm = _setup(tmp_path)
    idx = Indexer(vi, fi, llm)
    idx.reindex_doc("技术/漫剧.md", "介绍漫剧工具的使用方法")
    cfts.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="user",
        ts="2026-07-14T10:00:00",
        conversation_title="测试会话",
        chunks=[MessageChunk(0, 0, 4, "漫剧工具")],
    )
    retr = Retriever(vi, fi, llm, conversation_fts=cfts)

    hits = retr.search("漫剧工具", k=10)

    sources = {(h.doc_id, h.message_id) for h in hits}
    assert ("技术/漫剧.md", None) in sources
    assert any(h.message_id == "m1" for h in hits)
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)
