from app.index.chunk import chunk_starts, chunk_text
from app.index.indexer import Indexer
from app.index.vector import VectorIndex
from app.index.fulltext import FullTextIndex
from app.models.llm import FakeLLMClient


class CountingLLM(FakeLLMClient):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.embed_batch_sizes: list[int] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.embed_batch_sizes.append(len(texts))
        return super().embed(texts)


def _make(tmp_path, *, reindex_full_threshold: int = 4000):
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    llm = CountingLLM(embed_dim=8)
    idx = Indexer(vi, fi, llm, reindex_full_threshold=reindex_full_threshold)
    return idx, vi, fi, llm


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
    idx, vi, fi, _ = _make(tmp_path)
    idx.reindex_doc("doc1.md", "docker 容器常用命令，如何启动和停止")
    assert any(h.doc_id == "doc1.md" for h in fi.query("docker", k=5))
    q = FakeLLMClient(embed_dim=8).embed(["docker"])[0]
    assert any(h.doc_id == "doc1.md" for h in vi.query(q, k=5))


def test_reindex_twice_replaces(tmp_path):
    idx, vi, fi, _ = _make(tmp_path)
    idx.reindex_doc("doc1.md", "旧内容关于苹果")
    idx.reindex_doc("doc1.md", "新内容关于香蕉")
    assert fi.query("关于苹果", k=5) == []
    assert any(h.doc_id == "doc1.md" for h in fi.query("关于香蕉", k=5))


def test_remove_doc(tmp_path):
    idx, vi, fi, _ = _make(tmp_path)
    idx.reindex_doc("doc1.md", "docker 内容")
    idx.remove_doc("doc1.md")
    assert fi.query("docker", k=5) == []


def test_reindex_after_edit_partial_large_doc(tmp_path):
    idx, _, _, llm = _make(tmp_path, reindex_full_threshold=4000)
    body = _big_body()
    idx.reindex_doc("big.md", body)
    total_chunks = len(chunk_text(body))
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
    assert llm.embed_batch_sizes
    assert llm.embed_batch_sizes[-1] < total_chunks


def test_reindex_after_edit_small_doc_uses_full(tmp_path):
    idx, _, _, llm = _make(tmp_path, reindex_full_threshold=4000)
    body = "短文档内容"
    idx.reindex_doc("small.md", body)
    llm.embed_batch_sizes.clear()

    mode = idx.reindex_doc_after_edit("small.md", body, "新短文档内容", 0, 3)

    assert mode == "full"
    assert len(llm.embed_batch_sizes) == 1


def test_reindex_after_edit_searchable(tmp_path):
    idx, _, fi, _ = _make(tmp_path, reindex_full_threshold=4000)
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
    assert any(h.doc_id == "big.md" for h in fi.query("NEWTOKEN", k=5))
