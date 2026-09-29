from app.engine.retriever import Retriever
from app.index.conversation_index import ConversationIndex
from app.index.indexer import Indexer
from app.index.message_chunk import MessageChunk
from app.models.llm import FakeLLMClient
from tests.helpers import drain_embeddings, make_search_index


def _setup(tmp_path):
    llm = FakeLLMClient(embed_dim=8)
    si = make_search_index(tmp_path, llm)
    ci = ConversationIndex(si)
    return si, ci, llm


def test_retriever_includes_conversation_message_hits(tmp_path):
    si, ci, llm = _setup(tmp_path)
    ci.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="user",
        ts="2026-07-14T10:00:00",
        conversation_title="测试会话",
        chunks=[MessageChunk(0, 0, 4, "漫剧工具")],
    )
    retr = Retriever(si, llm)

    hits = retr.search("漫剧", k=5).hits

    assert hits
    hit = next(h for h in hits if h.message_id == "m1")
    assert hit.source == "conv:c1"
    assert hit.start_char == 0
    assert hit.end_char == 4
    assert hit.offset_version == "unicode-codepoint-v1"


def test_scope_knowledge_excludes_conversation_hits(tmp_path):
    si, ci, llm = _setup(tmp_path)
    ci.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="user",
        ts="t",
        conversation_title="",
        chunks=[MessageChunk(0, 0, 4, "漫剧工具")],
    )
    retr = Retriever(si, llm)

    hits = retr.search("漫剧", k=5, scope="knowledge").hits

    assert hits == []


def test_retriever_merges_kb_and_conversation_hits_sorted_by_score(tmp_path):
    si, ci, llm = _setup(tmp_path)
    idx = Indexer(si)
    idx.reindex_doc("技术/漫剧.md", "介绍漫剧工具的使用方法")
    drain_embeddings(si)
    ci.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="user",
        ts="2026-07-14T10:00:00",
        conversation_title="测试会话",
        chunks=[MessageChunk(0, 0, 4, "漫剧工具")],
    )
    retr = Retriever(si, llm)

    hits = retr.search("漫剧工具", k=10).hits

    sources = {(h.doc_id, h.message_id) for h in hits}
    assert ("技术/漫剧.md", None) in sources
    assert any(h.message_id == "m1" for h in hits)


def test_retriever_search_filters_conversation_hits_by_ts(tmp_path):
    si, ci, llm = _setup(tmp_path)
    ci.upsert_message_chunks(
        conversation_id="old",
        message_id="m-old",
        role="user",
        ts="2026-08-12T10:00:00+08:00",
        conversation_title="八月",
        chunks=[MessageChunk(0, 0, 5, "马尔可夫链")],
    )
    ci.upsert_message_chunks(
        conversation_id="yday",
        message_id="m-y",
        role="user",
        ts="2026-09-17T15:30:00+08:00",
        conversation_title="昨天",
        chunks=[MessageChunk(0, 0, 5, "马尔可夫链")],
    )
    retr = Retriever(si, llm)
    hits = retr.search(
        "马尔可夫链",
        k=5,
        scope="conversations",
        ts_after="2026-09-17",
        ts_before="2026-09-18",
    ).hits
    assert [h.message_id for h in hits] == ["m-y"]
