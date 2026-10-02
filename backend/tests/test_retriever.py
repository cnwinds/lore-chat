from app.engine.retriever import Retriever
from app.index.indexer import Indexer
from app.models.llm import FakeLLMClient
from tests.helpers import drain_embeddings, make_search_index


def _setup(tmp_path, chat_responses):
    llm = FakeLLMClient(chat_responses=chat_responses, embed_dim=8)
    si = make_search_index(tmp_path, llm)
    idx = Indexer(si)
    idx.reindex_doc("技术/docker/常用命令.md", "docker ps 查看容器，docker logs 看日志")
    idx.reindex_doc("生活/菜谱.md", "番茄炒蛋做法")
    drain_embeddings(si)
    retr = Retriever(si, llm)
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


def test_search_kb_prefixes(tmp_path):
    llm = FakeLLMClient(chat_responses=[], embed_dim=8)
    si = make_search_index(tmp_path, llm)
    idx = Indexer(si)
    idx.reindex_doc("技能/a.md", "docker ps 容器列表")
    idx.reindex_doc("笔记/b.md", "docker logs 日志")
    drain_embeddings(si)
    retr = Retriever(si, llm)
    hits = retr.search("docker", k=5, kb_prefixes=["技能/"]).hits
    assert hits
    assert all(h.doc_id.startswith("技能/") for h in hits)


def test_search_conversation_ids_empty_lane(tmp_path):
    llm = FakeLLMClient(chat_responses=[], embed_dim=8)
    si = make_search_index(tmp_path, llm)
    retr = Retriever(si, llm)
    page = retr.search("docker", k=5, scope="conversations", conversation_ids=[])
    assert page.hits == []


def test_answer_attaches_non_markdown(tmp_path):
    llm = FakeLLMClient(chat_responses=["见附件方案。"], embed_dim=8)
    si = make_search_index(tmp_path, llm)
    idx = Indexer(si)
    idx.reindex_doc("技术/docker/部署方案.pdf", "kubernetes 部署方案详细步骤")
    drain_embeddings(si)
    retr = Retriever(si, llm)
    ans = retr.answer("部署方案")
    assert "技术/docker/部署方案.pdf" in ans.attachments
