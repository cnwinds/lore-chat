from app.engine.retriever import Retriever
from app.index.vector import VectorIndex
from app.index.fulltext import FullTextIndex
from app.index.indexer import Indexer
from app.models.llm import FakeLLMClient


def _setup(tmp_path, chat_responses):
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    llm = FakeLLMClient(chat_responses=chat_responses, embed_dim=8)
    idx = Indexer(vi, fi, llm)
    idx.reindex_doc("技术/docker/常用命令.md", "docker ps 查看容器，docker logs 看日志")
    idx.reindex_doc("生活/菜谱.md", "番茄炒蛋做法")
    retr = Retriever(vi, fi, llm)
    return retr


def test_search_hybrid_finds_relevant(tmp_path):
    retr = _setup(tmp_path, [])
    hits = retr.search("docker", k=5).hits
    assert any(h.doc_id == "技术/docker/常用命令.md" for h in hits)


def test_search_dedups_by_doc(tmp_path):
    retr = _setup(tmp_path, [])
    hits = retr.search("docker", k=10).hits
    ids = [h.doc_id for h in hits]
    assert len(ids) == len(set(ids))  # 每个 doc 只出现一次


def test_search_filters_irrelevant_vector_hits(tmp_path):
    retr = _setup(tmp_path, [])
    hits = retr.search("Claude Opus 版本 4.8", k=5).hits
    assert hits == []


def test_answer_returns_sources(tmp_path):
    retr = _setup(tmp_path, ["docker logs 用于查看容器日志。"])
    ans = retr.answer("docker")
    assert "docker" in ans.text.lower()
    assert "技术/docker/常用命令.md" in ans.sources


def test_answer_attaches_readable_file(tmp_path):
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    llm = FakeLLMClient(chat_responses=["见附件方案。"], embed_dim=8)
    idx = Indexer(vi, fi, llm)
    idx.reindex_doc("技术/docker/attachments/部署方案.pdf", "kubernetes 部署方案详细步骤")
    retr = Retriever(vi, fi, llm)
    ans = retr.answer("部署方案")
    assert "技术/docker/attachments/部署方案.pdf" in ans.attachments
