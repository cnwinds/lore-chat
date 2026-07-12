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


def _make_registry(tmp_path, chat_responses=None, **settings_kw):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    llm = FakeLLMClient(chat_responses=chat_responses or [], embed_dim=8)
    idx = Indexer(vi, fi, llm)
    retr = Retriever(vi, fi, llm)
    pending = PendingStore(tmp_path / "knowledge" / ".kb" / "pending.json")
    settings = Settings(kb_path=tmp_path / "knowledge", **settings_kw)
    org = Organizer(repo=repo, retriever=retr, indexer=idx, pending=pending, llm=llm)
    fetcher = WebFetcher()
    web_search = WebSearch(settings)
    registry = ToolRegistry(
        retr,
        repo,
        org,
        fetcher,
        web_search,
        pending,
        indexer=idx,
        edit_doc_max_edits=settings.edit_doc_max_edits,
        edit_doc_max_patch_chars=settings.edit_doc_max_patch_chars,
        edit_doc_require_read=settings.edit_doc_require_read,
    )
    return registry, repo, idx


def test_can_parallelize_read_only():
    assert can_parallelize(["search_kb", "fetch_url"]) is True
    assert can_parallelize(["search_kb", "write_kb"]) is False
    assert can_parallelize(["search_kb", "delete_kb"]) is False
    assert can_parallelize(["search_kb", "edit_doc"]) is False


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
    result = await registry.execute("search_kb", {"query": "docker", "k": 5})
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


@pytest.mark.asyncio
async def test_read_doc_progressive_disclosure(tmp_path):
    registry, repo, _ = _make_registry(tmp_path)
    body = "# 大标题\n" + ("段落内容。" * 2000)  # 远超 3000 字
    repo.write_doc("技术/long.md", {"title": "长文"}, body, commit_msg="seed")

    first = await registry.execute("read_doc", {"path": "技术/long.md"})
    assert first["returned_chars"] <= 3000
    assert first["has_more"] is True
    assert first["offset"] == 0
    assert "outline" in first  # 首窗口附带结构大纲
    assert first["next_offset"] == first["returned_chars"]

    nxt = await registry.execute(
        "read_doc", {"path": "技术/long.md", "offset": first["next_offset"], "limit": 500}
    )
    assert nxt["offset"] == first["next_offset"]
    assert nxt["returned_chars"] <= 500


@pytest.mark.asyncio
async def test_delete_kb_doc(tmp_path):
    registry, repo, idx = _make_registry(tmp_path)
    repo.write_doc(
        "projects/mini-app/version-todo.md",
        {"title": "待办"},
        "待办内容\n",
        commit_msg="seed",
    )
    idx.reindex_doc("projects/mini-app/version-todo.md", "待办内容\n")
    result = await registry.execute(
        "delete_kb", {"path": "projects/mini-app/version-todo.md"}
    )
    assert "已删除" in result["summary"]
    assert result["deleted_paths"] == ["projects/mini-app/version-todo.md"]
    with pytest.raises(FileNotFoundError):
        repo.read_doc("projects/mini-app/version-todo.md")


@pytest.mark.asyncio
async def test_write_kb_exposes_structured_status(tmp_path):
    registry, repo, idx = _make_registry(tmp_path)
    result = await registry.execute("write_kb", {"text": "docker ps 查看容器列表"})
    assert result["status"] in {"saved", "question", "rejected"}
    if result["status"] == "saved":
        assert result["rel_path"]


@pytest.mark.asyncio
async def test_delete_kb_directory(tmp_path):
    registry, repo, idx = _make_registry(tmp_path)
    repo.write_doc(
        "projects/mini-app/version-todo.md",
        {"title": "待办"},
        "待办内容\n",
        commit_msg="seed",
    )
    idx.reindex_doc("projects/mini-app/version-todo.md", "待办内容\n")
    result = await registry.execute("delete_kb", {"path": "projects/mini-app/"})
    assert "已删除" in result["summary"]
    assert not (repo.root / "projects" / "mini-app").exists()


@pytest.mark.asyncio
async def test_edit_doc_requires_read_first(tmp_path):
    registry, repo, _ = _make_registry(tmp_path)
    repo.write_doc("技术/foo.md", {"title": "Foo"}, "hello world\n", commit_msg="seed")
    cid = "conv-1"
    result = await registry.execute(
        "edit_doc",
        {"path": "技术/foo.md", "edits": [{"old_string": "world", "new_string": "earth"}]},
        conversation_id=cid,
    )
    assert result.get("error") == "NOT_READ"
    assert result.get("status") == "failed"
    assert "read_doc" in (result.get("suggestion") or "")


@pytest.mark.asyncio
async def test_edit_doc_after_read(tmp_path):
    registry, repo, idx = _make_registry(tmp_path)
    path = "技术/foo.md"
    repo.write_doc(path, {"title": "Foo"}, "hello world\n", commit_msg="seed")
    idx.reindex_doc(path, "hello world\n")
    cid = "conv-2"
    await registry.execute("read_doc", {"path": path}, conversation_id=cid)
    result = await registry.execute(
        "edit_doc",
        {"path": path, "edits": [{"old_string": "world", "new_string": "earth"}]},
        conversation_id=cid,
    )
    assert "已" in result["summary"]
    assert result.get("error") is None
    assert result.get("status") == "saved"
    assert result.get("reindex_mode") in {"partial", "full"}
    assert repo.read_doc(path).body == "hello earth\n"


@pytest.mark.asyncio
async def test_edit_doc_protected_path(tmp_path):
    registry, repo, _ = _make_registry(tmp_path)
    cid = "conv-3"
    result = await registry.execute(
        "edit_doc",
        {"path": ".kb/pending.json", "edits": [{"old_string": "x", "new_string": "y"}]},
        conversation_id=cid,
    )
    assert result.get("error") == "PROTECTED"
    assert result.get("status") == "failed"


@pytest.mark.asyncio
async def test_edit_doc_system_precepts_allowed(tmp_path):
    registry, repo, idx = _make_registry(
        tmp_path,
        system_layer_dir="系统",
    )
    from app.engine.agent.system_layer import SystemLayer

    sl = SystemLayer(repo, dir_name="系统")
    sl.ensure_seeded()
    path = "系统/戒律.md"
    cid = "conv-4"
    await registry.execute("read_doc", {"path": path}, conversation_id=cid)
    original = repo.read_doc(path).body
    marker = "## 一、落库"
    result = await registry.execute(
        "edit_doc",
        {
            "path": path,
            "edits": [
                {
                    "old_string": marker,
                    "new_string": marker,
                }
            ],
        },
        conversation_id=cid,
    )
    assert result.get("error") is None
    assert result.get("status") == "saved"
    assert repo.read_doc(path).body == original


@pytest.mark.asyncio
async def test_edit_doc_edits_and_insert_mutually_exclusive(tmp_path):
    registry, repo, _ = _make_registry(tmp_path)
    path = "技术/foo.md"
    repo.write_doc(path, {"title": "Foo"}, "body\n", commit_msg="seed")
    cid = "conv-5"
    await registry.execute("read_doc", {"path": path}, conversation_id=cid)
    result = await registry.execute(
        "edit_doc",
        {
            "path": path,
            "edits": [{"old_string": "body", "new_string": "BODY"}],
            "insert": {"content": "extra\n"},
        },
        conversation_id=cid,
    )
    assert result.get("error") == "INVALID"
    assert result.get("status") == "failed"

