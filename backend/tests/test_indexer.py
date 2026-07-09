from app.index.indexer import Indexer
from app.index.vector import VectorIndex
from app.index.fulltext import FullTextIndex
from app.models.llm import FakeLLMClient


def _make(tmp_path):
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    llm = FakeLLMClient(embed_dim=8)
    return Indexer(vi, fi, llm), vi, fi


def test_reindex_adds_to_both(tmp_path):
    idx, vi, fi = _make(tmp_path)
    idx.reindex_doc("doc1.md", "docker 容器常用命令，如何启动和停止")
    assert any(h.doc_id == "doc1.md" for h in fi.query("docker", k=5))
    q = FakeLLMClient(embed_dim=8).embed(["docker"])[0]
    assert any(h.doc_id == "doc1.md" for h in vi.query(q, k=5))


def test_reindex_twice_replaces(tmp_path):
    idx, vi, fi = _make(tmp_path)
    idx.reindex_doc("doc1.md", "旧内容关于苹果")
    idx.reindex_doc("doc1.md", "新内容关于香蕉")
    assert fi.query("关于苹果", k=5) == []
    assert any(h.doc_id == "doc1.md" for h in fi.query("关于香蕉", k=5))


def test_remove_doc(tmp_path):
    idx, vi, fi = _make(tmp_path)
    idx.reindex_doc("doc1.md", "docker 内容")
    idx.remove_doc("doc1.md")
    assert fi.query("docker", k=5) == []
