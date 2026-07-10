import pytest

from app.config import Settings
from app.engine.agent.tools import ToolRegistry, can_parallelize
from app.engine.organizer import Organizer
from app.engine.pending import PendingStore
from app.engine.retriever import Retriever
from app.engine.web.fetcher import WebFetcher
from app.engine.web.search import WebSearch
from app.index.fulltext import FullTextIndex
from app.index.indexer import Indexer
from app.index.vector import VectorIndex
from app.models.llm import FakeLLMClient
from app.storage.repo import KnowledgeRepo


def _make_registry(tmp_path, chat_responses=None):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    llm = FakeLLMClient(chat_responses=chat_responses or [], embed_dim=8)
    idx = Indexer(vi, fi, llm)
    retr = Retriever(vi, fi, llm)
    pending = PendingStore(tmp_path / "knowledge" / ".kb" / "pending.json")
    settings = Settings(kb_path=tmp_path / "knowledge")
    org = Organizer(repo=repo, retriever=retr, indexer=idx, pending=pending, llm=llm)
    fetcher = WebFetcher()
    web_search = WebSearch(settings)
    registry = ToolRegistry(retr, repo, org, fetcher, web_search, pending)
    return registry, repo, idx


def test_can_parallelize_read_only():
    assert can_parallelize(["search_kb", "fetch_url"]) is True
    assert can_parallelize(["search_kb", "write_kb"]) is False


@pytest.mark.asyncio
async def test_search_kb_tool(tmp_path):
    registry, repo, idx = _make_registry(tmp_path)
    repo.write_doc(
        "技术/docker/常用命令.md",
        {"title": "常用命令"},
        "docker ps 查看容器，docker logs 看日志",
        commit_msg="seed",
    )
    idx.reindex_doc("技术/docker/常用命令.md", "docker ps 查看容器，docker logs 看日志")
    result = await registry.execute("search_kb", {"query": "docker 日志", "k": 5})
    assert "找到" in result["summary"]
    assert len(result["sources"]) >= 1
    assert result["sources"][0]["type"] == "kb"
    assert result["sources"][0]["path"] == "技术/docker/常用命令.md"
    assert "excerpt" in result["sources"][0]


@pytest.mark.asyncio
async def test_read_doc_not_found(tmp_path):
    registry, _, _ = _make_registry(tmp_path)
    result = await registry.execute("read_doc", {"path": "nope.md"})
    assert "不存在" in result["summary"]
    assert result.get("error")

