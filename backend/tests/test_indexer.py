from app.index.chunk import chunk_starts, chunk_text
from app.index.indexer import Indexer
from app.index.kb_index import KB_FAMILY, KB_PARTITION
from app.index.partitioned import PartitionTuning
from app.index.search_query import compile_search_query
from app.models.llm import FakeLLMClient
from tests.helpers import drain_embeddings, make_search_index


class CountingLLM(FakeLLMClient):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.embed_batch_sizes: list[int] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.embed_batch_sizes.append(len(texts))
        return super().embed(texts)


def _make(tmp_path, *, reindex_full_threshold: int = 4000):
    llm = CountingLLM(embed_dim=8)
    si = make_search_index(tmp_path, llm)
    idx = Indexer(si, reindex_full_threshold=reindex_full_threshold)
    return idx, si, llm


def _fts_query(si, text: str, k: int = 5):
    compiled = compile_search_query(text)
    res = si.search(
        text,
        partitions=[KB_PARTITION],
        limit=k,
        tunings={KB_FAMILY: PartitionTuning(fts_k=k, vec_k=k)},
        fts_mode="keywords",
        vector_text=compiled.vector_text,
        lanes=("fts",),
    )
    hits = res.lanes.get(f"{KB_FAMILY}:fts", [])
    return [h.meta.get("source") for h in hits]


def _big_body(marker: str = "UNIQUE_MARKER") -> str:
    return ("段" * 2500) + marker + ("落" * 2500)


def test_chunk_starts_aligns_with_chunk_text():
    text = "x" * 2500
    starts = chunk_starts(text)
    chunks = chunk_text(text)
    assert len(starts) == len(chunks)
    for start, chunk in zip(starts, chunks):
        assert text[start : start + len(chunk)] == chunk


def test_reindex_adds_to_both(tmp_path):
    idx, si, _ = _make(tmp_path)
    idx.reindex_doc("doc1.md", "docker 容器常用命令，如何启动和停止")
    assert "doc1.md" in _fts_query(si, "docker")
    drain_embeddings(si)
    compiled = compile_search_query("docker")
    res = si.search(
        "docker",
        partitions=[KB_PARTITION],
        limit=5,
        tunings={KB_FAMILY: PartitionTuning(fts_k=5, vec_k=5, min_vector_score=0.0)},
        fts_mode="keywords",
        vector_text=compiled.vector_text,
    )
    vec_sources = {h.meta.get("source") for h in res.lanes.get(f"{KB_FAMILY}:vec", [])}
    assert "doc1.md" in vec_sources


def test_reindex_twice_replaces(tmp_path):
    idx, si, _ = _make(tmp_path)
    idx.reindex_doc("doc1.md", "旧内容关于苹果")
    idx.reindex_doc("doc1.md", "新内容关于香蕉")
    assert "doc1.md" not in _fts_query(si, "关于苹果")
    assert "doc1.md" in _fts_query(si, "关于香蕉")


def test_remove_doc(tmp_path):
    idx, si, _ = _make(tmp_path)
    idx.reindex_doc("doc1.md", "docker 内容")
    idx.remove_doc("doc1.md")
    assert _fts_query(si, "docker") == []


def test_reindex_after_edit_partial_large_doc(tmp_path):
    idx, _, llm = _make(tmp_path, reindex_full_threshold=4000)
    body = _big_body()
    idx.reindex_doc("big.md", body)
    llm.embed_batch_sizes.clear()

    marker = "UNIQUE_MARKER"
    marker_pos = body.index(marker)
    new_body = body.replace(marker, "EDITED_TOKEN")
    mode = idx.reindex_doc_after_edit(
        "big.md",
        body,
        new_body,
        marker_pos,
        marker_pos + len(marker),
    )

    assert mode == "partial"
    assert llm.embed_batch_sizes == []


def test_reindex_after_edit_small_doc_uses_full(tmp_path):
    idx, _, llm = _make(tmp_path, reindex_full_threshold=4000)
    body = "短文档内容"
    idx.reindex_doc("small.md", body)
    llm.embed_batch_sizes.clear()

    mode = idx.reindex_doc_after_edit("small.md", body, "新短文档内容", 0, 3)

    assert mode == "full"
    assert llm.embed_batch_sizes == []


def test_reindex_after_edit_searchable(tmp_path):
    idx, si, _ = _make(tmp_path, reindex_full_threshold=4000)
    body = _big_body("OLDTOKEN")
    idx.reindex_doc("big.md", body)
    marker_pos = body.index("OLDTOKEN")
    new_body = body.replace("OLDTOKEN", "NEWTOKEN")

    mode = idx.reindex_doc_after_edit(
        "big.md",
        body,
        new_body,
        marker_pos,
        marker_pos + len("OLDTOKEN"),
    )

    assert mode == "partial"
    assert "big.md" in _fts_query(si, "NEWTOKEN")
