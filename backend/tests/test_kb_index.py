"""文档库分区索引：写入、编辑、检索与 reindex_doc_after_edit 返回值。"""

from app.index.chunk import chunk_text
from app.index.indexer import Indexer
from app.index.kb_index import KB_FAMILY, KB_PARTITION
from app.index.partitioned import PartitionTuning
from app.index.search_query import compile_search_query
from app.models.llm import FakeLLMClient
from tests.helpers import drain_embeddings, make_search_index


class CountingLLM(FakeLLMClient):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.embed_calls = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.embed_calls += len(texts)
        return super().embed(texts)

    def embed_with_model(self, texts: list[str]):
        self.embed_calls += len(texts)
        return super().embed_with_model(texts)


def _kb_fts_hits(search_index, query: str, *, k: int = 5):
    compiled = compile_search_query(query)
    res = search_index.search(
        query,
        partitions=[KB_PARTITION],
        limit=k,
        tunings={KB_FAMILY: PartitionTuning(fts_k=k, vec_k=k)},
        fts_mode="keywords",
        vector_text=compiled.vector_text,
        lanes=("fts",),
    )
    return res.lanes.get(f"{KB_FAMILY}:fts", [])


def _kb_vec_hits(search_index, query: str, *, k: int = 5):
    compiled = compile_search_query(query)
    res = search_index.search(
        query,
        partitions=[KB_PARTITION],
        limit=k,
        tunings={KB_FAMILY: PartitionTuning(fts_k=k, vec_k=k, min_vector_score=0.0)},
        fts_mode="keywords",
        vector_text=compiled.vector_text,
    )
    return res.lanes.get(f"{KB_FAMILY}:vec", [])


def test_write_then_fts_searchable_before_embed(tmp_path):
    si = make_search_index(tmp_path)
    idx = Indexer(si)
    idx.reindex_doc("doc1.md", "docker 容器常用命令，如何启动和停止")
    hits = _kb_fts_hits(si, "docker")
    sources = {h.meta["source"] for h in hits}
    assert "doc1.md" in sources


def test_write_drain_then_vector_searchable(tmp_path):
    si = make_search_index(tmp_path)
    idx = Indexer(si)
    idx.reindex_doc("doc1.md", "docker 容器常用命令，如何启动和停止")
    drain_embeddings(si)
    hits = _kb_vec_hits(si, "docker")
    sources = {h.meta["source"] for h in hits}
    assert "doc1.md" in sources


def test_edit_preserves_unchanged_chunk_vectors(tmp_path):
    llm = CountingLLM(embed_dim=8)
    si = make_search_index(tmp_path, llm)
    idx = Indexer(si, reindex_full_threshold=4000)
    body = ("段" * 2500) + "UNIQUE_MARKER" + ("落" * 2500)
    idx.reindex_doc("big.md", body)
    drain_embeddings(si)
    llm.embed_calls = 0

    marker = "UNIQUE_MARKER"
    pos = body.index(marker)
    new_body = body.replace(marker, "EDITED_TOKEN")
    mode = idx.reindex_doc_after_edit(
        "big.md", body, new_body, pos, pos + len(marker)
    )
    assert mode == "partial"

    starts = chunk_text(new_body)
    unchanged_ids = [f"big.md::{i}" for i in range(len(starts)) if "EDITED_TOKEN" not in starts[i]]
    for item_id in unchanged_ids[:3]:
        row = si._lexical.get_item(KB_PARTITION, item_id)
        assert row is not None
        assert row["vec_state"] == "ok"

    drain_embeddings(si)
    assert llm.embed_calls > 0
    assert llm.embed_calls < len(starts)


def test_remove_doc_not_searchable(tmp_path):
    si = make_search_index(tmp_path)
    idx = Indexer(si)
    idx.reindex_doc("doc1.md", "docker 内容")
    idx.remove_doc("doc1.md")
    assert _kb_fts_hits(si, "docker") == []


def test_system_layer_path_not_indexed(tmp_path):
    si = make_search_index(tmp_path)
    idx = Indexer(si, system_prefixes=("系统/",))
    idx.reindex_doc("系统/戒律.md", "不可索引的系统层内容")
    assert si.groups(KB_PARTITION) == []


def test_reindex_after_edit_return_values_match_thresholds(tmp_path):
    llm = CountingLLM(embed_dim=8)
    si = make_search_index(tmp_path, llm)
    idx = Indexer(si, reindex_full_threshold=4000)

    small = "短文档内容"
    idx.reindex_doc("small.md", small)
    assert idx.reindex_doc_after_edit("small.md", small, "新短文档内容", 0, 3) == "full"

    body = ("段" * 2500) + "UNIQUE_MARKER" + ("落" * 2500)
    idx.reindex_doc("big.md", body)
    marker = "UNIQUE_MARKER"
    pos = body.index(marker)
    new_body = body.replace(marker, "EDITED_TOKEN")
    assert (
        idx.reindex_doc_after_edit("big.md", body, new_body, pos, pos + len(marker))
        == "partial"
    )


def test_two_char_chinese_keyword_hits_doc(tmp_path):
    si = make_search_index(tmp_path)
    idx = Indexer(si)
    idx.reindex_doc("运营/材料.md", "面向教培机构的合作会谈材料，强调数据本地部署。")
    hits = _kb_fts_hits(si, "教培机构")
    assert any("教培机构" in h.text for h in hits)
    hits_coop = _kb_fts_hits(si, "合作")
    assert any("合作" in h.text for h in hits_coop)


def test_fts_keywords_with_markdown_special_chars_no_syntax_error(tmp_path):
    si = make_search_index(tmp_path)
    idx = Indexer(si)
    idx.reindex_doc("doc.md", "PowerShell 配置 `$PROFILE` 路径")
    q = "```powershell\n$PROFILE = `$env:USERPROFILE`"
    compiled = compile_search_query(q)
    res = si.search(
        q,
        partitions=[KB_PARTITION],
        limit=5,
        tunings={KB_FAMILY: PartitionTuning(fts_k=5, vec_k=5)},
        fts_mode="keywords",
        vector_text=compiled.vector_text,
        lanes=("fts",),
    )
    assert isinstance(res.lanes.get(f"{KB_FAMILY}:fts", []), list)


def test_retriever_cursor_and_match_strength_unchanged(tmp_path):
    from app.engine.retriever import Retriever
    from app.index.revision import IndexRevision

    llm = FakeLLMClient(embed_dim=8)
    si = make_search_index(tmp_path, llm)
    idx = Indexer(si)
    idx.reindex_doc("技术/漫剧.md", "介绍漫剧工具的使用方法")
    drain_embeddings(si)
    rev = IndexRevision(tmp_path / "rev.txt")
    retr = Retriever(si, llm, index_revision=rev, min_score=0.0)

    page1 = retr.search("漫剧工具", k=1, scope="knowledge")
    assert page1.match_strength == "strong"
    assert page1.hits
    assert page1.index_revision == rev.get()

    stale = "forged-or-rev-stale-token"
    page2 = retr.search("漫剧工具", k=1, scope="knowledge", cursor=stale)
    assert page2.cursor_expired
