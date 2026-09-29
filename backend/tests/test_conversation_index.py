"""ConversationIndex 与会话检索（分区底座）。"""

from app.engine.retriever import Retriever
from app.index.conversation_index import CONV_PARTITION, ConversationIndex
from app.index.indexer import Indexer
from app.index.message_chunk import MessageChunk
from app.models.llm import FakeLLMClient
from tests.helpers import conv_fts_hits, drain_embeddings, make_search_index


class CountingLLM(FakeLLMClient):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.embed_calls = 0

    def embed_with_model(self, texts: list[str]):
        self.embed_calls += len(texts)
        return self.embed(texts), f"fake-embed-{self.embed_dim}"


def test_upsert_then_fts_searchable(tmp_path):
    si = make_search_index(tmp_path)
    ci = ConversationIndex(si)
    ci.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="user",
        ts="2026-01-01T00:00:00",
        conversation_title="t",
        chunks=[MessageChunk(0, 0, 4, "会话关键词")],
    )
    hits = conv_fts_hits(si, "关键词")
    assert len(hits) == 1
    assert hits[0].meta["conversation_id"] == "c1"


def test_drain_then_vector_searchable(tmp_path):
    llm = FakeLLMClient(embed_dim=8)
    si = make_search_index(tmp_path, llm)
    ci = ConversationIndex(si)
    ci.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="user",
        ts="t",
        conversation_title="",
        chunks=[MessageChunk(0, 0, 6, "向量检索")],
    )
    drain_embeddings(si)
    from app.index.partitioned import PartitionTuning
    from app.index.search_query import compile_search_query

    compiled = compile_search_query("向量")
    res = si.search(
        "向量",
        partitions=[CONV_PARTITION],
        limit=5,
        tunings={
            "conv": PartitionTuning(fts_k=5, vec_k=5, min_vector_score=0.0)
        },
        fts_mode="keywords",
        vector_text=compiled.vector_text,
    )
    assert res.lanes.get("conv:vec", [])


def test_rewrite_removes_extra_chunks(tmp_path):
    si = make_search_index(tmp_path)
    ci = ConversationIndex(si)
    ci.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="user",
        ts="t",
        conversation_title="",
        chunks=[
            MessageChunk(0, 0, 2, "ab"),
            MessageChunk(1, 2, 4, "cd"),
        ],
    )
    ci.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="user",
        ts="t",
        conversation_title="",
        chunks=[MessageChunk(0, 0, 2, "ab")],
    )
    items = si.group_items(CONV_PARTITION, "c1/m1")
    assert len(items) == 1


def test_delete_conversation_prefix_safe(tmp_path):
    si = make_search_index(tmp_path)
    ci = ConversationIndex(si)
    for mid in ("m1", "m2"):
        ci.upsert_message_chunks(
            conversation_id="c1",
            message_id=mid,
            role="user",
            ts="t",
            conversation_title="",
            chunks=[MessageChunk(0, 0, 2, "x")],
        )
    ci.upsert_message_chunks(
        conversation_id="c10",
        message_id="m1",
        role="user",
        ts="t",
        conversation_title="",
        chunks=[MessageChunk(0, 0, 2, "y")],
    )
    ci.delete_conversation("c1")
    assert "c10" in ci.conversation_ids()
    assert "c1" not in ci.conversation_ids()


def test_covered_ranges_sorted(tmp_path):
    si = make_search_index(tmp_path)
    ci = ConversationIndex(si)
    ci.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="user",
        ts="t",
        conversation_title="",
        chunks=[
            MessageChunk(1, 10, 20, "b"),
            MessageChunk(0, 0, 5, "a"),
        ],
    )
    assert ci.covered_ranges("c1", "m1") == [(0, 5), (10, 20)]


def test_retriever_filters_and_two_char_keyword(tmp_path):
    llm = FakeLLMClient(embed_dim=8)
    si = make_search_index(tmp_path, llm)
    ci = ConversationIndex(si)
    ci.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="user",
        ts="2026-09-17T10:00:00",
        conversation_title="",
        chunks=[MessageChunk(0, 0, 4, "教培机构")],
    )
    ci.upsert_message_chunks(
        conversation_id="c2",
        message_id="m2",
        role="user",
        ts="2026-08-01T10:00:00",
        conversation_title="",
        chunks=[MessageChunk(0, 0, 4, "教培机构")],
    )
    retr = Retriever(si, llm, min_score=0.0)
    page = retr.search(
        "教培机构",
        k=5,
        scope="conversations",
        conversation_id="c1",
    )
    assert len(page.hits) == 1
    assert page.hits[0].source == "conv:c1"

    page2 = retr.search(
        "教培机构",
        k=5,
        scope="conversations",
        ts_after="2026-09-01",
        ts_before="2026-10-01",
    )
    assert len(page2.hits) == 1
    assert page2.hits[0].message_id == "m1"


def test_retriever_excludes_active_conversation(tmp_path):
    llm = FakeLLMClient(embed_dim=8)
    si = make_search_index(tmp_path, llm)
    ci = ConversationIndex(si)
    for cid, mid, title in (
        ("current", "m1", "当前"),
        ("past", "m2", "历史"),
    ):
        ci.upsert_message_chunks(
            conversation_id=cid,
            message_id=mid,
            role="user",
            ts="t",
            conversation_title=title,
            chunks=[MessageChunk(0, 0, 4, "人脑结构")],
        )
    retr = Retriever(si, llm, min_score=0.0)
    page = retr.search(
        "人脑",
        k=5,
        scope="conversations",
        exclude_conversation_id="current",
    )
    assert len(page.hits) == 1
    assert page.hits[0].source == "conv:past"
    assert page.hits[0].conversation_title == "历史"


def test_scope_all_embeds_at_most_once(tmp_path):
    llm = CountingLLM(embed_dim=8)
    si = make_search_index(tmp_path, llm)
    idx = Indexer(si)
    ci = ConversationIndex(si)
    idx.reindex_doc("doc.md", "知识库文档内容")
    ci.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="user",
        ts="t",
        conversation_title="",
        chunks=[MessageChunk(0, 0, 6, "会话内容")],
    )
    drain_embeddings(si)
    llm.embed_calls = 0
    retr = Retriever(si, llm, min_score=0.0)
    retr.search("内容", k=5, scope="all")
    assert llm.embed_calls == 1
