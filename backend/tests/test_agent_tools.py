import pytest

from app.config import Settings
from app.engine.agent.prompts import MODE_DEFAULT, MODE_FORCE_WRITE, MODE_NO_WRITE
from app.engine.agent.tools import ToolRegistry, can_parallelize, select_tools
from app.engine.organizer import Organizer
from app.engine.pending import PendingStore
from app.engine.retriever import Retriever
from app.engine.web.fetcher import WebFetcher
from app.engine.web.search import WebSearch
from app.engine.conversations import ConversationStore
from app.index.conversation_fts import ConversationFTS
from app.index.fulltext import FullTextIndex
from app.index.indexer import Indexer
from app.index.message_chunk import MessageChunk
from app.index.revision import IndexRevision
from app.index.vector import VectorIndex
from app.models.llm import FakeLLMClient
from app.storage.repo import KnowledgeRepo


def _make_registry(tmp_path, chat_responses=None, conversation_fts=None, conversations=None, **settings_kw):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    llm = FakeLLMClient(chat_responses=chat_responses or [], embed_dim=8)
    idx = Indexer(vi, fi, llm)
    rev = IndexRevision(tmp_path / "revision.txt")
    retr = Retriever(vi, fi, llm, conversation_fts=conversation_fts, index_revision=rev)
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
        conversations=conversations,
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
async def test_search_kb_returns_conversation_source_with_message_fields(tmp_path):
    cfts = ConversationFTS(tmp_path / "conversation_fts.db")
    cfts.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="user",
        ts="2026-07-14T10:00:00",
        conversation_title="测试会话",
        chunks=[MessageChunk(0, 0, 4, "漫剧工具")],
    )
    registry, _repo, _idx = _make_registry(tmp_path, conversation_fts=cfts)
    result = await registry.execute("search_kb", {"query": "漫剧工具", "k": 5})
    conv_sources = [s for s in result["sources"] if s["type"] == "conversation"]
    assert conv_sources, result["sources"]
    src = conv_sources[0]
    assert src["cid"] == "c1"
    assert src["message_id"] == "m1"
    assert src["start_char"] == 0
    assert src["end_char"] == 4
    assert src["offset_version"] == "unicode-codepoint-v1"
    assert src["role"] == "user"
    assert src["ts"] == "2026-07-14T10:00:00"
    assert src["conversation_title"] == "测试会话"
    assert "excerpt" in src


@pytest.mark.asyncio
async def test_search_kb_excludes_active_conversation_by_default(tmp_path):
    cfts = ConversationFTS(tmp_path / "conversation_fts.db")
    cfts.upsert_message_chunks(
        conversation_id="current",
        message_id="m-current",
        role="user",
        ts="2026-07-14T12:00:00",
        conversation_title="当前会话",
        chunks=[MessageChunk(0, 0, 4, "人脑结构")],
    )
    cfts.upsert_message_chunks(
        conversation_id="past",
        message_id="m-past",
        role="user",
        ts="2026-07-10T10:00:00",
        conversation_title="历史会话",
        chunks=[MessageChunk(0, 0, 4, "人脑结构")],
    )
    registry, _repo, _idx = _make_registry(tmp_path, conversation_fts=cfts)
    result = await registry.execute(
        "search_kb",
        {"query": "人脑结构", "k": 5, "scope": "conversations"},
        conversation_id="current",
    )
    conv_sources = [s for s in result["sources"] if s["type"] == "conversation"]
    assert len(conv_sources) == 1
    assert conv_sources[0]["cid"] == "past"
    assert conv_sources[0]["conversation_title"] == "历史会话"


@pytest.mark.asyncio
async def test_search_kb_explicit_conversation_id_searches_within_session(tmp_path):
    cfts = ConversationFTS(tmp_path / "conversation_fts.db")
    cfts.upsert_message_chunks(
        conversation_id="current",
        message_id="m-current",
        role="user",
        ts="2026-07-14T12:00:00",
        conversation_title="当前会话",
        chunks=[MessageChunk(0, 0, 4, "人脑结构")],
    )
    cfts.upsert_message_chunks(
        conversation_id="past",
        message_id="m-past",
        role="user",
        ts="2026-07-10T10:00:00",
        conversation_title="历史会话",
        chunks=[MessageChunk(0, 0, 4, "人脑结构")],
    )
    registry, _repo, _idx = _make_registry(tmp_path, conversation_fts=cfts)
    result = await registry.execute(
        "search_kb",
        {
            "query": "人脑结构",
            "k": 5,
            "scope": "conversations",
            "conversation_id": "current",
        },
        conversation_id="current",
    )
    conv_sources = [s for s in result["sources"] if s["type"] == "conversation"]
    assert len(conv_sources) == 1
    assert conv_sources[0]["cid"] == "current"


@pytest.mark.asyncio
async def test_read_conversation_context_tool(tmp_path):
    store = ConversationStore(tmp_path / "knowledge" / ".kb" / "conversations")
    cid = store.create()
    turn = store.begin_turn(
        cid,
        user_text="cursor key 借出记录",
        client_message_id="ctx-1",
        observation_allowed=False,
    )
    store.finalize_turn(
        cid,
        turn_id=turn["turn_id"],
        assistant={
            "text": "已记录借出",
            "timeline": [],
            "sources": [],
            "status": "complete",
        },
    )
    message_id = store.get(cid)["messages"][0]["id"]
    registry, _repo, _idx = _make_registry(tmp_path, conversations=store)
    result = await registry.execute(
        "read_conversation_context",
        {
            "conversation_id": cid,
            "message_id": message_id,
            "before_messages": 0,
            "after_messages": 1,
        },
    )
    assert "messages" in result
    assert len(result["messages"]) >= 1
    assert "cursor key" in result["messages"][0]["text"]


@pytest.mark.asyncio
async def test_search_kb_scope_conversations(tmp_path):
    cfts = ConversationFTS(tmp_path / "conversation_fts.db")
    cfts.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="user",
        ts="t",
        conversation_title="",
        chunks=[MessageChunk(0, 0, 4, "漫剧工具")],
    )
    registry, repo, idx = _make_registry(tmp_path, conversation_fts=cfts)
    repo.write_doc("技术/漫剧.md", {"title": "漫剧"}, "漫剧工具文档", commit_msg="seed")
    idx.reindex_doc("技术/漫剧.md", "漫剧工具文档")

    result = await registry.execute(
        "search_kb", {"query": "漫剧", "k": 5, "scope": "conversations"}
    )
    assert all(s["type"] == "conversation" for s in result["sources"])


@pytest.mark.asyncio
async def test_search_kb_reports_cursor_expired(tmp_path):
    from app.engine.retriever import _make_cursor

    registry, _, _ = _make_registry(tmp_path)
    stale = _make_cursor("q", {"scope": "all", "conversation_id": None}, 999, 0)
    result = await registry.execute("search_kb", {"query": "q", "k": 1, "cursor": stale})
    assert result.get("cursor_expired") is True
    assert "过期" in result["summary"]


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
    result = await registry.execute(
        "write_kb",
        {
            "text": "docker ps 查看容器列表",
            "directory": "技术/docker",
            "filename": "常用命令.md",
        },
    )
    assert result["status"] == "saved"
    assert result["rel_path"] == "技术/docker/常用命令.md"
    assert repo.read_doc("技术/docker/常用命令.md").body


@pytest.mark.asyncio
async def test_write_kb_requires_directory_and_filename(tmp_path):
    registry, _, _ = _make_registry(tmp_path)
    result = await registry.execute("write_kb", {"text": "hello"})
    assert result["error"] == "MISSING_PATH"


@pytest.mark.asyncio
async def test_move_doc_tool(tmp_path):
    registry, repo, idx = _make_registry(tmp_path)
    path = "llm/old-name.md"
    repo.write_doc(path, {"title": "Old"}, "body\n", commit_msg="seed")
    idx.reindex_doc(path, "body\n")
    result = await registry.execute(
        "move_doc",
        {
            "from_path": path,
            "to_directory": "技术/llm",
            "to_filename": "new-name.md",
        },
    )
    assert result["status"] == "saved"
    assert result["rel_path"] == "技术/llm/new-name.md"
    repo.read_doc("技术/llm/new-name.md")
    with pytest.raises(FileNotFoundError):
        repo.read_doc(path)


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


@pytest.mark.asyncio
async def test_edit_doc_insert_after_heading(tmp_path):
    registry, repo, idx = _make_registry(tmp_path)
    path = "技术/deploy.md"
    body = "# 部署\n\n## 步骤\n原有\n"
    repo.write_doc(path, {"title": "Deploy"}, body, commit_msg="seed")
    idx.reindex_doc(path, body)
    cid = "conv-insert-1"
    await registry.execute("read_doc", {"path": path}, conversation_id=cid)
    result = await registry.execute(
        "edit_doc",
        {
            "path": path,
            "insert": {"after_heading": "## 步骤", "content": "新增一行\n"},
        },
        conversation_id=cid,
    )
    assert result.get("status") == "saved"
    assert "新增一行" in repo.read_doc(path).body
    assert result.get("preview")


@pytest.mark.asyncio
async def test_edit_doc_insert_append(tmp_path):
    registry, repo, _ = _make_registry(tmp_path)
    path = "技术/note.md"
    repo.write_doc(path, {"title": "Note"}, "base\n", commit_msg="seed")
    cid = "conv-insert-2"
    await registry.execute("read_doc", {"path": path}, conversation_id=cid)
    result = await registry.execute(
        "edit_doc",
        {"path": path, "insert": {"content": "more\n"}},
        conversation_id=cid,
    )
    assert result.get("status") == "saved"
    assert repo.read_doc(path).body.endswith("more\n")


def _tool_names(defs):
    return {d["function"]["name"] for d in defs}


def test_select_tools_web_disabled_drops_web_search():
    names = _tool_names(select_tools(MODE_DEFAULT, web_enabled=False))
    assert "web_search" not in names
    assert "fetch_url" in names


def test_select_tools_web_enabled_keeps_web_search():
    names = _tool_names(select_tools(MODE_DEFAULT, web_enabled=True))
    assert "web_search" in names


def test_select_tools_no_write_drops_write_kb():
    names = _tool_names(select_tools(MODE_NO_WRITE, web_enabled=True))
    assert "write_kb" not in names


def test_select_tools_force_write_keeps_write_kb():
    names = _tool_names(select_tools(MODE_FORCE_WRITE, web_enabled=True))
    assert "write_kb" in names

