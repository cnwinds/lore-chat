from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import Settings
from app.models.cooldown import CooldownStore
from app.engine.agent.prompts import MODE_DEFAULT, MODE_FORCE_WRITE, MODE_NO_WRITE
from app.engine.agent.tools import ToolRegistry, can_parallelize, select_tools
from app.engine.disclosure import DisclosureWindows
from app.engine.organizer import Organizer
from app.engine.pending import PendingStore
from app.engine.retriever import Retriever
from app.engine.web.fetcher import WebFetcher
from app.engine.web.search import SearchResult, WebSearch
from app.engine.conversations import ConversationStore
from app.engine.enabled_skills import EnabledSkillsStore
from app.index.indexer import Indexer
from app.index.message_chunk import MessageChunk
from app.index.revision import IndexRevision
from app.models.llm import FakeLLMClient
from app.storage.repo import KnowledgeRepo
from app.engine.roles import RoleStore
from tests.helpers import make_conversation_index, make_search_index, make_writer


def _wire_registry_context(registry, tmp_path, *, conversations=None):
    from app.engine.channel_plugins.store import ChannelInstanceStore
    from app.engine.conversations import ConversationStore
    from app.engine.memory.cards import KnowledgeCards
    from app.engine.memory.service import MemoryService
    from app.engine.memory.store import MemoryStore
    from app.engine.roles import RoleStore

    kb = tmp_path / "knowledge"
    roles = RoleStore(tmp_path / "roles")
    conv = conversations or ConversationStore(kb / ".kb" / "conversations")
    channel_instances = ChannelInstanceStore(kb)
    owner = MemoryService(
        MemoryStore(tmp_path / "memory.db", owner_key="ws1"),
        registry.repo,
        knowledge_writer=registry.knowledge_writer,
    )
    cards = KnowledgeCards(
        tmp_path / "memory.db",
        owner=owner,
        roles=roles,
        conversations=conv,
        channel_instances=channel_instances,
    )
    registry.context_view.cards = cards
    registry.context_view.roles = roles
    registry.context_view.conversations = conv
    registry.context_view.channel_instances = channel_instances
    if registry.conversations is None:
        registry.conversations = conv
    registry.kb_read.conversations = conv
    registry.kb_mutate.cards = cards
    registry.kb_mutate.channel_instances = channel_instances
    registry.kb_mutate.roles = roles
    return roles, conv


def _conv_uri(conv, cid, *, message_id=None):
    from app.engine.context_view.uri import ConversationUri, format_uri

    rid = conv.get_role_id(cid)
    return format_uri(
        ConversationUri("dm", rid, cid, message_id, message_id is None)
    )



def _make_registry(tmp_path, chat_responses=None, conversation_index=None, conversations=None, **settings_kw):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    llm = FakeLLMClient(chat_responses=chat_responses or [], embed_dim=8)
    if conversation_index is not None:
        si = conversation_index.search_index
    else:
        si = make_search_index(tmp_path, llm)
    idx = Indexer(si)
    rev = IndexRevision(tmp_path / "revision.txt")
    retr = Retriever(si, llm, index_revision=rev)
    pending = PendingStore(tmp_path / "knowledge" / ".kb" / "pending.json")
    settings = Settings(kb_path=tmp_path / "knowledge", **settings_kw)
    writer = make_writer(repo, tmp_path)
    org = Organizer(
        repo=repo,
        retriever=retr,
        pending=pending,
        llm=llm,
        knowledge_writer=writer,
    )
    fetcher = WebFetcher()
    web_search = WebSearch(settings, cooldown=CooldownStore(settings.kb_path / '.kb' / 'search_cd.json'))
    registry = ToolRegistry(
        retr,
        repo,
        org,
        fetcher,
        web_search,
        pending,
        writer,
        conversations=conversations,
        indexer=idx,
        edit_doc_max_edits=settings.edit_doc_max_edits,
        edit_doc_max_patch_chars=settings.edit_doc_max_patch_chars,
        edit_doc_require_read=settings.edit_doc_require_read,
        web_search_default_k=settings.web_search_default_k,
        roles=RoleStore(tmp_path / "roles"),
    )
    _wire_registry_context(registry, tmp_path, conversations=conversations)
    return registry, repo, idx


def test_can_parallelize_read_only():
    assert can_parallelize(["search", "fetch_url"]) is True
    assert can_parallelize(["search", "write_doc"]) is False
    assert can_parallelize(["search", "delete_kb"]) is False
    assert can_parallelize(["search", "edit_doc"]) is False
    assert can_parallelize(["generate_image", "generate_image"]) is True
    assert can_parallelize(["generate_image", "search"]) is True
    assert can_parallelize(["generate_image", "write_doc"]) is False
    assert can_parallelize(["send_message", "send_message"]) is True
    assert can_parallelize(["send_message", "search"]) is True
    assert can_parallelize(["send_message", "write_doc"]) is False


@pytest.mark.asyncio
async def test_search_tool(tmp_path):
    registry, repo, idx = _make_registry(tmp_path)
    repo.write_doc(
        "技术/docker/常用命令.md",
        {"title": "常用命令"},
        "docker ps 查看容器，docker logs 看日志",
        commit_msg="seed",
    )
    idx.reindex_doc("技术/docker/常用命令.md", "docker ps 查看容器，docker logs 看日志")
    result = await registry.execute("search", {"query": "docker", "k": 5})
    assert "找到" in result["summary"]
    assert len(result["sources"]) >= 1
    assert result["sources"][0]["type"] == "kb"
    assert result["sources"][0]["path"] == "技术/docker/常用命令.md"
    assert "excerpt" in result["sources"][0]


@pytest.mark.asyncio
async def test_search_returns_conversation_source_with_message_fields(tmp_path):
    store = ConversationStore(tmp_path / "knowledge" / ".kb" / "conversations")
    cid = store.create()
    ci = make_conversation_index(tmp_path)
    ci.upsert_message_chunks(
        conversation_id=cid,
        message_id="m1",
        role="user",
        ts="2026-07-14T10:00:00",
        conversation_title="测试会话",
        chunks=[MessageChunk(0, 0, 4, "漫剧工具")],
    )
    registry, _repo, _idx = _make_registry(
        tmp_path, conversation_index=ci, conversations=store
    )
    result = await registry.execute(
        "search",
        {
            "query": "漫剧工具",
            "k": 5,
            "paths": [f"lore://conversations/dm/default/{cid}/"],
        },
        conversation_id=cid,
    )
    conv_sources = [s for s in result["sources"] if s["type"] == "conversation"]
    assert conv_sources, result["sources"]
    src = conv_sources[0]
    assert src["cid"] == cid
    assert src["message_id"] == "m1"
    assert src["start_char"] == 0
    assert src["end_char"] == 4
    assert src["offset_version"] == "unicode-codepoint-v1"
    assert src["role"] == "user"
    assert src["ts"] == "2026-07-14T10:00:00"
    assert src["conversation_title"] == "测试会话"
    assert "excerpt" in src


@pytest.mark.asyncio
async def test_search_excludes_active_conversation_by_default(tmp_path):
    store = ConversationStore(tmp_path / "knowledge" / ".kb" / "conversations")
    current = store.create()
    past = store.create()
    ci = make_conversation_index(tmp_path)
    ci.upsert_message_chunks(
        conversation_id=current,
        message_id="m-current",
        role="user",
        ts="2026-07-14T12:00:00",
        conversation_title="当前会话",
        chunks=[MessageChunk(0, 0, 4, "人脑结构")],
    )
    ci.upsert_message_chunks(
        conversation_id=past,
        message_id="m-past",
        role="user",
        ts="2026-07-10T10:00:00",
        conversation_title="历史会话",
        chunks=[MessageChunk(0, 0, 4, "人脑结构")],
    )
    registry, _repo, _idx = _make_registry(
        tmp_path, conversation_index=ci, conversations=store
    )
    result = await registry.execute(
        "search",
        {
            "query": "人脑结构",
            "k": 5,
            "paths": ["lore://conversations/dm/~/"],
        },
        conversation_id=current,
    )
    conv_sources = [s for s in result["sources"] if s["type"] == "conversation"]
    assert len(conv_sources) == 1
    assert conv_sources[0]["cid"] == past
    assert conv_sources[0]["conversation_title"] == "历史会话"


@pytest.mark.asyncio
async def test_search_explicit_conversation_id_searches_within_session(tmp_path):
    store = ConversationStore(tmp_path / "knowledge" / ".kb" / "conversations")
    current = store.create()
    past = store.create()
    ci = make_conversation_index(tmp_path)
    ci.upsert_message_chunks(
        conversation_id=current,
        message_id="m-current",
        role="user",
        ts="2026-07-14T12:00:00",
        conversation_title="当前会话",
        chunks=[MessageChunk(0, 0, 4, "人脑结构")],
    )
    ci.upsert_message_chunks(
        conversation_id=past,
        message_id="m-past",
        role="user",
        ts="2026-07-10T10:00:00",
        conversation_title="历史会话",
        chunks=[MessageChunk(0, 0, 4, "人脑结构")],
    )
    registry, _repo, _idx = _make_registry(
        tmp_path, conversation_index=ci, conversations=store
    )
    result = await registry.execute(
        "search",
        {
            "query": "人脑结构",
            "k": 5,
            "paths": [f"lore://conversations/dm/default/{current}/"],
        },
        conversation_id=current,
    )
    conv_sources = [s for s in result["sources"] if s["type"] == "conversation"]
    assert len(conv_sources) == 1
    assert conv_sources[0]["cid"] == current


@pytest.mark.asyncio
async def test_read_tool(tmp_path):
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
        "read",
        {
            "uri": _conv_uri(store, cid, message_id=message_id),
            "before": 0,
            "after": 1,
        },
        conversation_id=cid,
    )
    assert "messages" in result
    assert len(result["messages"]) >= 1
    assert "cursor key" in result["messages"][0]["text"]


@pytest.mark.asyncio
async def test_read_defaults_to_prior_segment(tmp_path):
    store = ConversationStore(tmp_path / "knowledge" / ".kb" / "conversations")
    prior = store.create()
    store.append_exchange(prior, "先做新闻视频方案", {"role": "assistant", "text": "已记下月报流程"})
    current = store.create()
    registry, _repo, _idx = _make_registry(tmp_path, conversations=store)
    result = await registry.execute(
        "read",
        {"uri": _conv_uri(store, prior)},
        conversation_id=current,
    )
    texts = " ".join(m["text"] for m in result["messages"])
    assert "新闻视频方案" in texts
    assert result["anchor"]["conversation_id"] == prior


@pytest.mark.asyncio
async def test_search_scope_conversations(tmp_path):
    ci = make_conversation_index(tmp_path)
    ci.upsert_message_chunks(
        conversation_id="c1",
        message_id="m1",
        role="user",
        ts="t",
        conversation_title="",
        chunks=[MessageChunk(0, 0, 4, "漫剧工具")],
    )
    registry, repo, idx = _make_registry(tmp_path, conversation_index=ci)
    repo.write_doc("技术/漫剧.md", {"title": "漫剧"}, "漫剧工具文档", commit_msg="seed")
    idx.reindex_doc("技术/漫剧.md", "漫剧工具文档")

    result = await registry.execute(
        "search", {"query": "漫剧", "k": 5, "paths": ["lore://conversations/"]}
    )
    assert all(s["type"] == "conversation" for s in result["sources"])


@pytest.mark.asyncio
async def test_search_filters_conversations_by_ts_range(tmp_path):
    store = ConversationStore(tmp_path / "knowledge" / ".kb" / "conversations")
    old = store.create()
    yesterday = store.create()
    ci = make_conversation_index(tmp_path)
    ci.upsert_message_chunks(
        conversation_id=old,
        message_id="m-old",
        role="user",
        ts="2026-08-12T10:00:00+08:00",
        conversation_title="八月游戏",
        chunks=[MessageChunk(0, 0, 5, "马尔可夫链")],
    )
    ci.upsert_message_chunks(
        conversation_id=yesterday,
        message_id="m-y",
        role="user",
        ts="2026-09-17T15:00:00+08:00",
        conversation_title="新闻视频",
        chunks=[MessageChunk(0, 0, 5, "马尔可夫链")],
    )
    registry, _repo, _idx = _make_registry(
        tmp_path, conversation_index=ci, conversations=store
    )
    result = await registry.execute(
        "search",
        {
            "query": "马尔可夫链",
            "k": 5,
            "paths": ["lore://conversations/"],
            "ts_after": "2026-09-17",
            "ts_before": "2026-09-18",
        },
    )
    conv_sources = [s for s in result["sources"] if s["type"] == "conversation"]
    assert len(conv_sources) == 1
    assert conv_sources[0]["cid"] == yesterday


@pytest.mark.asyncio
async def test_search_reports_cursor_expired(tmp_path):
    registry, _, _ = _make_registry(tmp_path)
    stale = "eyJxIjoicSIsImYiOnsic2NvcGUiOiJhbGwifX0="  # 伪造的旧式游标
    result = await registry.execute("search", {"query": "q", "k": 1, "cursor": stale})
    assert result.get("cursor_expired") is True
    assert "过期" in result["summary"]


@pytest.mark.asyncio
async def test_read_not_found(tmp_path):
    registry, _, _ = _make_registry(tmp_path)
    result = await registry.execute("read", {"uri": "nope.md"})
    assert "不存在" in result["summary"]
    assert result.get("error")


@pytest.mark.asyncio
async def test_read_progressive_disclosure(tmp_path):
    registry, repo, _ = _make_registry(tmp_path)
    body = "# 大标题\n" + ("段落内容。" * 2000)  # 远超 3000 字
    repo.write_doc("技术/long.md", {"title": "长文"}, body, commit_msg="seed")

    first = await registry.execute("read", {"uri": "技术/long.md"})
    assert first["returned_chars"] <= 3000
    assert first["has_more"] is True
    assert first["offset"] == 0
    assert "outline" in first  # 首窗口附带结构大纲
    assert first["next_offset"] == first["returned_chars"]

    nxt = await registry.execute(
        "read", {"uri": "技术/long.md", "offset": first["next_offset"], "limit": 500}
    )
    assert nxt["offset"] == first["next_offset"]
    assert nxt["returned_chars"] <= 500


@pytest.mark.asyncio
async def test_read_deep_intent_larger_window(tmp_path):
    registry, repo, _ = _make_registry(tmp_path)
    body = "# 大标题\n" + ("段落内容。" * 8000)
    repo.write_doc("技术/long.md", {"title": "长文"}, body, commit_msg="seed")

    deep = await registry.execute(
        "read", {"uri": "技术/long.md", "intent": "deep"}
    )
    assert deep["returned_chars"] > 3000
    assert deep["returned_chars"] <= 16000

    capped = await registry.execute(
        "read",
        {"uri": "技术/long.md", "intent": "deep", "limit": 999999},
    )
    assert capped["returned_chars"] == 32000

    # 问答取证不得借大 limit 绕过小窗
    spot = await registry.execute(
        "read",
        {"uri": "技术/long.md", "intent": "spot", "limit": 20000},
    )
    assert spot["returned_chars"] <= 3000


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
async def test_write_doc_exposes_structured_status(tmp_path):
    registry, repo, idx = _make_registry(tmp_path)
    result = await registry.execute(
        "write_doc",
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
async def test_write_doc_requires_directory_and_filename(tmp_path):
    registry, _, _ = _make_registry(tmp_path)
    result = await registry.execute("write_doc", {"text": "hello"})
    assert result["error"] == "MISSING_PATH"


@pytest.mark.asyncio
async def test_move_entry_tool(tmp_path):
    registry, repo, idx = _make_registry(tmp_path)
    path = "llm/old-name.md"
    repo.write_doc(path, {"title": "Old"}, "body\n", commit_msg="seed")
    idx.reindex_doc(path, "body\n")
    result = await registry.execute(
        "move_entry",
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
async def test_move_entry_directory(tmp_path):
    registry, repo, idx = _make_registry(tmp_path)
    repo.write_doc(
        "技能/old-pkg/SKILL.md",
        {"title": "S"},
        "body\n",
        commit_msg="seed",
    )
    repo.write_doc(
        "技能/old-pkg/references/a.md",
        {"title": "A"},
        "ref\n",
        commit_msg="seed",
    )
    idx.reindex_doc("技能/old-pkg/SKILL.md", "body\n")
    idx.reindex_doc("技能/old-pkg/references/a.md", "ref\n")
    result = await registry.execute(
        "move_entry",
        {
            "from_path": "技能/old-pkg",
            "to_directory": "技能",
            "to_filename": "new-pkg",
        },
    )
    assert result["status"] == "saved"
    assert result["rel_path"] == "技能/new-pkg"
    repo.read_doc("技能/new-pkg/SKILL.md")
    repo.read_doc("技能/new-pkg/references/a.md")
    assert not (repo.root / "技能" / "old-pkg").exists()


@pytest.mark.asyncio
async def test_delete_kb_skill_package_prunes_enabled_set(tmp_path):
    registry, repo, _ = _make_registry(tmp_path)
    repo.write_doc(
        "技能/gone/SKILL.md",
        {"title": "gone"},
        "---\nname: gone\ndescription: Use gone.\n---\n\n# g\n",
        commit_msg="seed",
    )
    store = EnabledSkillsStore(repo.root, skills_dir="技能")
    store.save_roots(["技能/gone"])
    result = await registry.execute("delete_kb", {"path": "技能/gone"})
    assert "已删除" in result["summary"]
    assert store.load_roots() == []


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
    store = ConversationStore(tmp_path / "knowledge" / ".kb" / "conversations")
    cid = store.create()
    registry, repo, _ = _make_registry(tmp_path, conversations=store)
    repo.write_doc("技术/foo.md", {"title": "Foo"}, "hello world\n", commit_msg="seed")
    result = await registry.execute(
        "edit_doc",
        {"path": "技术/foo.md", "edits": [{"old_string": "world", "new_string": "earth"}]},
        conversation_id=cid,
    )
    assert result.get("error") == "NOT_READ"
    assert result.get("status") == "failed"
    assert "read" in (result.get("suggestion") or "")


@pytest.mark.asyncio
async def test_edit_doc_after_read(tmp_path):
    store = ConversationStore(tmp_path / "knowledge" / ".kb" / "conversations")
    cid = store.create()
    registry, repo, idx = _make_registry(tmp_path, conversations=store)
    path = "技术/foo.md"
    repo.write_doc(path, {"title": "Foo"}, "hello world\n", commit_msg="seed")
    idx.reindex_doc(path, "hello world\n")
    await registry.execute("read", {"uri": path}, conversation_id=cid)
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
    store = ConversationStore(tmp_path / "knowledge" / ".kb" / "conversations")
    cid = store.create()
    registry, repo, _ = _make_registry(tmp_path, conversations=store)
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
    store = ConversationStore(tmp_path / "knowledge" / ".kb" / "conversations")
    cid = store.create()
    registry.conversations = store
    registry.context_view.conversations = store
    await registry.execute("read", {"uri": path}, conversation_id=cid)
    original = repo.read_doc(path).body
    marker = "## 一、总原则"
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
    store = ConversationStore(tmp_path / "knowledge" / ".kb" / "conversations")
    cid = store.create()
    registry, repo, _ = _make_registry(tmp_path, conversations=store)
    path = "技术/foo.md"
    repo.write_doc(path, {"title": "Foo"}, "body\n", commit_msg="seed")
    await registry.execute("read", {"uri": path}, conversation_id=cid)
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
    store = ConversationStore(tmp_path / "knowledge" / ".kb" / "conversations")
    cid = store.create()
    registry.conversations = store
    registry.context_view.conversations = store
    await registry.execute("read", {"uri": path}, conversation_id=cid)
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
    store = ConversationStore(tmp_path / "knowledge" / ".kb" / "conversations")
    cid = store.create()
    registry, repo, _ = _make_registry(tmp_path, conversations=store)
    path = "技术/note.md"
    repo.write_doc(path, {"title": "Note"}, "base\n", commit_msg="seed")
    await registry.execute("read", {"uri": path}, conversation_id=cid)
    result = await registry.execute(
        "edit_doc",
        {"path": path, "insert": {"content": "more\n"}},
        conversation_id=cid,
    )
    assert result.get("status") == "saved"
    assert repo.read_doc(path).body.endswith("more\n")


def _tool_names(defs):
    return {d["function"]["name"] for d in defs}


@pytest.mark.asyncio
async def test_web_search_tool_invokes_searcher(tmp_path):
    """属性与方法不能同名 web_search，否则会 TypeError: not callable。"""
    registry, _, _ = _make_registry(tmp_path)
    mock = MagicMock()
    mock.provider_name = "tavily"
    mock.search = AsyncMock(
        return_value=(
            [SearchResult(title="A", url="https://a.example", snippet="snip")],
            None,
        )
    )
    registry.web_search = mock
    result = await registry.execute("web_search", {"query": "DeepSeek API 涨价", "k": 3})
    assert "搜索到 1 条" in result["summary"]
    assert result["sources"][0]["url"] == "https://a.example"
    mock.search.assert_awaited_once_with("DeepSeek API 涨价", k=3)


@pytest.mark.asyncio
async def test_web_search_uses_settings_default_k(tmp_path):
    registry, _, _ = _make_registry(tmp_path, web_search_default_k=8)
    mock = MagicMock()
    mock.provider_name = "tavily"
    mock.search = AsyncMock(return_value=([], None))
    registry.web_search = mock
    await registry.execute("web_search", {"query": "test"})
    mock.search.assert_awaited_once_with("test", k=8)


def test_select_tools_injects_disclosure_window_numbers():
    tools = select_tools(
        MODE_DEFAULT,
        web_enabled=True,
        disclosure_windows=DisclosureWindows(spot=1111, deep=2222, max_chars=3333),
    )
    by_name = {t["function"]["name"]: t for t in tools}
    read_desc = by_name["read"]["function"]["description"]
    assert "1111" in read_desc and "2222" in read_desc and "3333" in read_desc
    limit_desc = by_name["read"]["function"]["parameters"]["properties"]["limit"][
        "description"
    ]
    assert "1111" in limit_desc and "3333" in limit_desc
    fetch_desc = by_name["fetch_url"]["function"]["description"]
    assert "1111" in fetch_desc


def test_select_tools_web_disabled_drops_web_search():
    names = _tool_names(select_tools(MODE_DEFAULT, web_enabled=False))
    assert "web_search" not in names
    assert "fetch_url" in names


def test_select_tools_web_enabled_keeps_web_search():
    names = _tool_names(select_tools(MODE_DEFAULT, web_enabled=True))
    assert "web_search" in names


def test_select_tools_web_enabled_but_no_provider_drops_web_search():
    names = _tool_names(
        select_tools(MODE_DEFAULT, web_enabled=True, search_configured=False)
    )
    assert "web_search" not in names
    assert "fetch_url" in names


def test_select_tools_imagegen_gate():
    names_on = _tool_names(
        select_tools(MODE_DEFAULT, web_enabled=True, imagegen_configured=True)
    )
    names_off = _tool_names(
        select_tools(MODE_DEFAULT, web_enabled=True, imagegen_configured=False)
    )
    assert "generate_image" in names_on
    assert "generate_image" not in names_off
    names_nw = _tool_names(
        select_tools(MODE_NO_WRITE, web_enabled=True, imagegen_configured=True)
    )
    assert "generate_image" not in names_nw


def test_select_tools_no_write_drops_write_doc():
    names = _tool_names(select_tools(MODE_NO_WRITE, web_enabled=True))
    assert "write_doc" not in names


def test_select_tools_force_write_keeps_write_doc():
    names = _tool_names(select_tools(MODE_FORCE_WRITE, web_enabled=True))
    assert "write_doc" in names


def test_kb_planning_tool_descriptions_match_precepts():
    from app.engine.agent.tool_catalog import TOOL_DEFINITIONS

    defs = {d["function"]["name"]: d["function"] for d in TOOL_DEFINITIONS}
    list_desc = defs["list"]["description"]
    write_desc = defs["write_doc"]["description"]
    move_desc = defs["move_entry"]["description"]
    assert "知识库目录" in list_desc
    assert "规划新的知识库路径" in list_desc and "必须先 list 目标目录" in list_desc
    assert "并入已知文档" in list_desc
    assert "写入前先 list" not in write_desc
    assert "并入已知文档沿用已确认路径时不必再为选路径调用" in write_desc
    assert "须先 list" in move_desc
    assert "建议 list" not in move_desc
    assert "to_filename" not in defs["move_entry"]["parameters"]["required"]
    assert "省略" in move_desc


def test_list_roles_is_readonly_and_describes_catalog():
    from app.engine.agent.tool_catalog import (
        READ_ONLY_TOOLS,
        TOOL_DEFINITIONS,
        TOOL_LABELS,
    )

    defs = {d["function"]["name"]: d["function"] for d in TOOL_DEFINITIONS}
    desc = defs["list_roles"]["description"]
    assert "list_roles" in READ_ONLY_TOOLS
    assert "列出角色" == TOOL_LABELS["list_roles"]
    assert "禁止凭印象编造角色名单" in desc
    assert "role_id" in defs["list_roles"]["parameters"]["properties"]
    assert "name" in defs["list_roles"]["parameters"]["properties"]
    assert "先调用 list_roles" in defs["create_role"]["description"]
    names = _tool_names(select_tools(MODE_NO_WRITE, web_enabled=True))
    assert "list_roles" in names


def test_ask_user_contract_requires_tool_not_prose():
    from app.engine.agent.tool_catalog import TOOL_DEFINITIONS

    defs = {d["function"]["name"]: d["function"] for d in TOOL_DEFINITIONS}
    desc = defs["ask_user"]["description"]
    assert "提问卡片" in desc
    assert "必须调用" in desc
    assert "禁止把问题或选项写进正文" in desc
    assert "input" in desc
    assert "不要再为同一问题追问一遍" in desc
    opt_props = defs["ask_user"]["parameters"]["properties"]["options"]["items"][
        "properties"
    ]
    assert "input" in opt_props
    names = _tool_names(select_tools(MODE_DEFAULT, web_enabled=True, role_messaging=True))
    assert "ask_user" in names


def test_cross_segment_continuity_contract():
    from app.engine.agent.tool_catalog import TOOL_DEFINITIONS

    defs = {d["function"]["name"]: d["function"] for d in TOOL_DEFINITIONS}
    ctx = defs["read"]
    assert "history" in ctx["description"]
    assert "分隔线" in ctx["description"]
    assert ctx["parameters"]["required"] == []
    assert "uris" in ctx["parameters"]["properties"]
    search = defs["search"]
    assert "上一会话段" in search["description"]
    assert "相关度" in search["description"]
    assert "read" in search["description"] or "list" in search["description"]
    assert "ts_after" in search["parameters"]["properties"]
    assert "ts_before" in search["parameters"]["properties"]
    archive = defs["summarize_conversation"]
    assert "conversation_id" in archive["parameters"]["properties"]
    assert "conversation_id" not in archive["parameters"]["required"]
    assert "默认归档当前段" in archive["description"]
    assert "本次会话" not in archive["description"]
    names = _tool_names(select_tools(MODE_DEFAULT, web_enabled=True, role_messaging=True))
    assert "ask_user" in names


def test_role_avatar_tool_accepts_kb_path_and_default_role_update():
    from app.engine.agent.tool_catalog import TOOL_DEFINITIONS

    defs = {d["function"]["name"]: d["function"] for d in TOOL_DEFINITIONS}
    create_avatar = defs["create_role"]["parameters"]["properties"]["avatar"][
        "description"
    ]
    update_avatar = defs["update_role"]["parameters"]["properties"]["avatar"][
        "description"
    ]
    update_desc = defs["update_role"]["description"]
    assert "相对路径" in create_avatar
    assert "相对路径" in update_avatar
    assert "rel_path" in update_avatar
    assert "不能修改默认角色的核心属性" not in update_desc
    assert "默认角色也可以改" in update_desc


@pytest.mark.asyncio
async def test_list_tool(tmp_path):
    registry, repo, idx = _make_registry(tmp_path)
    repo.write_doc(
        "技术/docker/常用命令.md",
        {"title": "常用命令"},
        "docker ps",
        commit_msg="seed",
    )
    result = await registry.execute("list", {"uri": "lore://kb/技术/"})
    names = {e.get("name") for e in result.get("entries", [])}
    assert "docker" in names or any("docker" in (e.get("name") or "") for e in result["entries"])


@pytest.mark.asyncio
async def test_list_omits_binaries_and_truncates(tmp_path):
    registry, repo, _ = _make_registry(tmp_path)
    repo.write_bytes("媒体/shot.png", b"\x89PNG\r\n", commit_msg="png")
    for i in range(201):
        repo.write_doc(
            f"备忘/n{i:02d}.md",
            {"title": f"n{i}"},
            f"body {i}\n",
            commit_msg="seed",
        )
    listed = await registry.execute("list", {"uri": "lore://kb/备忘/"})
    entry_names = [e.get("name") for e in listed.get("entries", [])]
    assert "shot.png" not in entry_names
    assert listed.get("has_more") is True
    assert len(entry_names) == 200


def test_legacy_read_tools_removed_from_catalog():
    from app.engine.agent.tool_catalog import (
        READ_ONLY_TOOLS,
        TOOL_DEFINITIONS,
        TOOL_LABELS,
    )
    from app.engine.agent.tool_dispatch import build_tool_dispatch

    legacy = {
        "search_kb",
        "read_doc",
        "read_doc_meta",
        "list_kb_structure",
        "read_conversation_context",
        "recall_memory",
        "recall_cards",
    }
    names = {d["function"]["name"] for d in TOOL_DEFINITIONS}
    assert legacy.isdisjoint(names)
    assert legacy.isdisjoint(TOOL_LABELS)
    assert legacy.isdisjoint(READ_ONLY_TOOLS)
    reg = ToolRegistry(
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )
    dispatch = build_tool_dispatch(reg)
    assert legacy.isdisjoint(dispatch)


@pytest.mark.asyncio
async def test_write_doc_accepts_lore_kb_uri(tmp_path):
    registry, repo, _ = _make_registry(tmp_path)
    result = await registry.execute(
        "write_doc",
        {
            "text": "hello",
            "directory": "lore://kb/技术/docker",
            "filename": "uri-test.md",
        },
    )
    assert result.get("status") == "saved"
    assert repo.read_doc("技术/docker/uri-test.md").body


@pytest.mark.asyncio
async def test_write_doc_rejects_conversation_uri(tmp_path):
    registry, _, _ = _make_registry(tmp_path)
    result = await registry.execute(
        "write_doc",
        {
            "text": "x",
            "directory": "lore://conversations/dm/r/c1",
            "filename": "bad.md",
        },
    )
    assert result.get("error") == "read_only_uri"
    assert "uri" in result


@pytest.mark.asyncio
async def test_write_doc_rejects_conversation_scheme_directory(tmp_path):
    registry, _, _ = _make_registry(tmp_path)
    result = await registry.execute(
        "write_doc",
        {
            "text": "x",
            "directory": "conversation://abc123",
            "filename": "bad.md",
        },
    )
    assert result.get("error") == "read_only_uri"
    assert result.get("uri") == "conversation://abc123"


@pytest.mark.asyncio
async def test_summarize_hidden_api_role_dm_returns_not_found(tmp_path):
    from app.engine.roles import VISIBILITY_HIDDEN

    store = ConversationStore(tmp_path / "knowledge" / ".kb" / "conversations")
    roles = RoleStore(tmp_path / "roles")
    persona = roles.create_persona(name="P", system_prompt="")
    hidden_role = roles.create(
        name="隐藏通道",
        system_prompt="",
        visibility=VISIBILITY_HIDDEN,
        persona_id=persona["id"],
        role_id="api_hidden_test",
    )
    hidden_cid = store.create(role_id=hidden_role["id"])
    owner_cid = store.create()
    registry, _, _ = _make_registry(tmp_path, conversations=store)
    called = {"n": 0}

    def _boom(*a, **k):
        called["n"] += 1
        raise AssertionError("organizer should not run")

    registry.organizer.summarize_conversation = _boom
    result = await registry.execute(
        "summarize_conversation",
        {
            "directory": "归档",
            "filename": "x.md",
            "conversation_id": hidden_cid,
        },
        conversation_id=owner_cid,
    )
    assert result.get("error") == "not_found"
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_summarize_conversation_rejects_channel_on_owner_turn(tmp_path):
    from app.engine.channel_plugins.store import ChannelInstanceStore
    from app.engine.roles import RoleStore

    store = ConversationStore(tmp_path / "knowledge" / ".kb" / "conversations")
    roles = RoleStore(tmp_path / "roles")
    role = roles.create(name="通道", system_prompt="")
    inst = ChannelInstanceStore(tmp_path / "knowledge").create(
        type_id="script_api",
        name="ch",
        persona_id=roles.create_persona(name="P", system_prompt="")["id"],
        role_id=role["id"],
    )
    channel_cid = store.create(
        role_id=role["id"], origin="api", channel_instance_id=inst["id"]
    )
    owner_cid = store.create()
    registry, _, _ = _make_registry(tmp_path, conversations=store)
    called = {"n": 0}

    def _boom(*a, **k):
        called["n"] += 1
        raise AssertionError("organizer should not run")

    registry.organizer.summarize_conversation = _boom
    result = await registry.execute(
        "summarize_conversation",
        {
            "directory": "归档",
            "filename": "x.md",
            "conversation_id": f"conversation://{channel_cid}",
        },
        conversation_id=owner_cid,
    )
    assert result.get("error") == "out_of_scope"
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_summarize_conversation_out_of_scope(tmp_path):
    from app.engine.channel_plugins.store import ChannelInstanceStore
    from app.engine.roles import RoleStore

    store = ConversationStore(tmp_path / "knowledge" / ".kb" / "conversations")
    roles = RoleStore(tmp_path / "roles")
    role = roles.create(name="通道", system_prompt="")
    inst = ChannelInstanceStore(tmp_path / "knowledge").create(
        type_id="script_api",
        name="ch",
        persona_id=roles.create_persona(name="P", system_prompt="")["id"],
        role_id=role["id"],
    )
    current = store.create(
        role_id=role["id"], origin="api", channel_instance_id=inst["id"]
    )
    other = store.create(
        role_id=role["id"], origin="api", channel_instance_id=inst["id"]
    )
    registry, _, _ = _make_registry(tmp_path, conversations=store)
    called = {"n": 0}

    def _boom(*a, **k):
        called["n"] += 1
        raise AssertionError("organizer should not run")

    registry.organizer.summarize_conversation = _boom
    result = await registry.execute(
        "summarize_conversation",
        {
            "directory": "归档",
            "filename": "x.md",
            "conversation_id": other,
        },
        conversation_id=current,
    )
    assert result.get("error") == "out_of_scope"
    assert called["n"] == 0


