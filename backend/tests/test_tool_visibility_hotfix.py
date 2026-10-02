"""ADR 2026-10-02 落地顺序第 0 步：工具可见性热修。"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.config import Settings
from app.engine.agent.prompts import MODE_API
from app.engine.agent.tool_catalog import select_tools
from app.engine.agent.tool_loop import AgentToolLoop
from app.engine.agent.tool_progress import ToolProgressExecutor
from app.engine.agent.tools import ToolRegistry
from app.engine.conversation_context import read_conversation_context
from app.engine.conversations import ConversationStore
from app.engine.organizer import Organizer
from app.engine.pending import PendingStore
from app.engine.retriever import Retriever
from app.engine.web.fetcher import WebFetcher
from app.engine.web.search import WebSearch
from app.index.indexer import Indexer
from app.index.message_chunk import MessageChunk
from app.models.cooldown import CooldownStore
from app.models.llm import FakeLLMClient, ToolCall
from app.storage.repo import KnowledgeRepo
from tests.helpers import make_conversation_index, make_search_index, make_writer


def _store(tmp_path):
    return ConversationStore(tmp_path / "knowledge" / ".kb" / "conversations")


def _build_loop(tmp_path, llm: FakeLLMClient) -> tuple[AgentToolLoop, ToolRegistry]:
    kb = tmp_path / "knowledge"
    settings = Settings(kb_path=kb)
    repo = KnowledgeRepo(kb)
    si = make_search_index(tmp_path, llm)
    idx = Indexer(si)
    retr = Retriever(si, llm)
    pending = PendingStore(kb / ".kb" / "pending.json")
    writer = make_writer(repo, tmp_path)
    org = Organizer(
        repo=repo,
        retriever=retr,
        pending=pending,
        llm=llm,
        knowledge_writer=writer,
    )
    registry = ToolRegistry(
        retr,
        repo,
        org,
        WebFetcher(5, 1000),
        WebSearch(settings, cooldown=CooldownStore(settings.kb_path / ".kb" / "search_cd.json")),
        pending,
        writer,
    )
    return AgentToolLoop(settings, llm, registry), registry


@pytest.mark.asyncio
async def test_tool_loop_rejects_unoffered_tool_without_dispatch(tmp_path):
    llm = FakeLLMClient(
        tool_responses=[
            {
                "content": None,
                "tool_calls": [
                    ToolCall(id="1", name="write_doc", arguments={"path": "x.md", "body": "pwn"}),
                ],
            },
            {"content": "done", "tool_calls": []},
        ],
        embed_dim=8,
    )
    loop, registry = _build_loop(tmp_path, llm)
    original = registry.execute
    mock_execute = AsyncMock(wraps=original)
    registry.execute = mock_execute
    loop._tool_progress = ToolProgressExecutor(mock_execute)

    tools_for_run = [
        {
            "type": "function",
            "function": {"name": "search", "description": "d", "parameters": {}},
        }
    ]
    events: list[str] = []
    async for ev in loop.stream(
        [{"role": "user", "content": "q"}],
        tools_for_run=tools_for_run,
        conversation_id="cid",
        active_doc_path=None,
    ):
        events.append(ev)

    mock_execute.assert_not_awaited()
    result_events = [e for e in events if "event: tool_result" in e]
    assert len(result_events) == 1
    assert "本回合未提供该工具：write_doc" in result_events[0]


@pytest.mark.asyncio
async def test_tool_loop_runs_offered_tool(tmp_path):
    llm = FakeLLMClient(
        tool_responses=[
            {
                "content": None,
                "tool_calls": [
                    ToolCall(id="1", name="search", arguments={"query": "hello", "k": 1}),
                ],
            },
            {"content": "done", "tool_calls": []},
        ],
        embed_dim=8,
    )
    loop, registry = _build_loop(tmp_path, llm)
    original = registry.execute
    mock_execute = AsyncMock(wraps=original)
    registry.execute = mock_execute
    loop._tool_progress = ToolProgressExecutor(mock_execute)

    tools_for_run = [
        {
            "type": "function",
            "function": {"name": "search", "description": "d", "parameters": {}},
        }
    ]
    async for _ in loop.stream(
        [{"role": "user", "content": "q"}],
        tools_for_run=tools_for_run,
        conversation_id="cid",
        active_doc_path=None,
    ):
        pass

    mock_execute.assert_awaited_once()
    assert mock_execute.await_args.args[0] == "search"


def test_select_tools_api_includes_search_not_legacy_recall():
    names = {d["function"]["name"] for d in select_tools(MODE_API, web_enabled=False)}
    assert "search" in names
    assert "recall_memory" not in names
    assert "recall_cards" not in names


def test_read_context_owner_cannot_read_channel_conversation(tmp_path):
    store = _store(tmp_path)
    channel = store.create(origin="api")
    store.append_exchange(channel, "外部消息", {"role": "assistant", "text": "收到"})
    owner = store.create()
    out = read_conversation_context(
        store,
        conversation_id=channel,
        current_conversation_id=owner,
    )
    assert out["error"] == "forbidden"
    assert out["messages"] == []


def test_read_context_channel_cannot_read_other_conversation(tmp_path):
    store = _store(tmp_path)
    other = store.create(origin="api")
    store.append_exchange(other, "A", {"role": "assistant", "text": "a"})
    current = store.create(origin="feishu")
    store.append_exchange(current, "B", {"role": "assistant", "text": "b"})
    out = read_conversation_context(
        store,
        conversation_id=other,
        current_conversation_id=current,
    )
    assert out["error"] == "forbidden"


def test_read_context_channel_can_read_self(tmp_path):
    store = _store(tmp_path)
    current = store.create(origin="api")
    store.append_exchange(current, "仅本会话", {"role": "assistant", "text": "ok"})
    out = read_conversation_context(
        store,
        conversation_id=current,
        current_conversation_id=current,
    )
    assert out.get("error") is None
    assert "仅本会话" in " ".join(m["text"] for m in out["messages"])


def test_read_context_owner_can_read_owner_dm(tmp_path):
    store = _store(tmp_path)
    dm = store.create()
    store.append_exchange(dm, "主人私聊", {"role": "assistant", "text": "好"})
    out = read_conversation_context(
        store,
        conversation_id=dm,
        current_conversation_id=store.create(),
    )
    assert out.get("error") is None
    assert "主人私聊" in " ".join(m["text"] for m in out["messages"])


def _channel_pair(tmp_path):
    from app.engine.channel_plugins.store import ChannelInstanceStore
    from app.engine.roles import RoleStore

    kb = tmp_path / "knowledge"
    store = _store(tmp_path)
    roles = RoleStore(tmp_path / "roles")
    role = roles.create(name="通道", system_prompt="")
    persona = roles.create_persona(name="P", system_prompt="")
    inst = ChannelInstanceStore(kb).create(
        type_id="script_api",
        name="ch",
        persona_id=persona["id"],
        role_id=role["id"],
    )
    channel_a = store.create(
        role_id=role["id"], origin="api", channel_instance_id=inst["id"]
    )
    channel_b = store.create(
        role_id=role["id"], origin="api", channel_instance_id=inst["id"]
    )
    return store, inst["id"], channel_a, channel_b


@pytest.mark.asyncio
async def test_search_kb_channel_turn_pins_conversation_id(tmp_path):
    from tests.test_agent_tools import _make_registry

    ci = make_conversation_index(tmp_path)
    store, inst_id, channel_a, channel_b = _channel_pair(tmp_path)
    ci.upsert_message_chunks(
        conversation_id=channel_a,
        message_id="m-a",
        role="user",
        ts="2026-07-14T12:00:00",
        conversation_title="A",
        chunks=[MessageChunk(0, 0, 4, "共享词")],
    )
    ci.upsert_message_chunks(
        conversation_id=channel_b,
        message_id="m-b",
        role="user",
        ts="2026-07-14T12:00:00",
        conversation_title="B",
        chunks=[MessageChunk(0, 0, 4, "共享词")],
    )

    registry, _repo, _idx = _make_registry(
        tmp_path, conversation_index=ci, conversations=store
    )
    with patch.object(
        registry.context_view.retriever,
        "search",
        wraps=registry.context_view.retriever.search,
    ) as mock_search:
        await registry.execute(
            "search",
            {
                "query": "共享词",
                "k": 5,
                "paths": [
                    f"lore://conversations/channels/{inst_id}/{channel_a}/"
                ],
            },
            conversation_id=channel_a,
        )
        mock_search.assert_called()
        kwargs = mock_search.call_args.kwargs
        assert kwargs.get("cursor_binding") == channel_a
        conv_ids = kwargs.get("conversation_ids")
        assert conv_ids is not None
        assert channel_a in conv_ids
        assert channel_b not in conv_ids


@pytest.mark.asyncio
async def test_channel_default_search_does_not_hit_other_thread(tmp_path):
    from tests.test_agent_tools import _make_registry

    ci = make_conversation_index(tmp_path)
    store, inst_id, channel_a, channel_b = _channel_pair(tmp_path)
    unique_b = "乙通道独有检索词"
    ci.upsert_message_chunks(
        conversation_id=channel_b,
        message_id="m-b-only",
        role="user",
        ts="2026-07-14T12:00:00",
        conversation_title="B",
        chunks=[MessageChunk(0, 0, len(unique_b), unique_b)],
    )
    ci.upsert_message_chunks(
        conversation_id=channel_a,
        message_id="m-a",
        role="user",
        ts="2026-07-14T12:00:00",
        conversation_title="A",
        chunks=[MessageChunk(0, 0, 2, "无关")],
    )
    registry, _repo, _idx = _make_registry(
        tmp_path, conversation_index=ci, conversations=store
    )
    with patch.object(
        registry.context_view.retriever,
        "search",
        wraps=registry.context_view.retriever.search,
    ) as mock_search:
        result = await registry.execute(
            "search",
            {"query": unique_b, "k": 5},
            conversation_id=channel_a,
        )
    conv_sources = [s for s in result["sources"] if s["type"] == "conversation"]
    assert not any(s.get("cid") == channel_b for s in conv_sources)
    if mock_search.called:
        kwargs = mock_search.call_args.kwargs
        conv_ids = kwargs.get("conversation_ids")
        if conv_ids is not None:
            assert channel_b not in conv_ids


@pytest.mark.asyncio
async def test_channel_search_explicit_other_thread_out_of_scope_no_retriever(tmp_path):
    from tests.test_agent_tools import _make_registry

    ci = make_conversation_index(tmp_path)
    store, inst_id, channel_a, channel_b = _channel_pair(tmp_path)
    registry, _repo, _idx = _make_registry(
        tmp_path, conversation_index=ci, conversations=store
    )
    with patch.object(registry.context_view.retriever, "search") as mock_search:
        r_lore = await registry.execute(
            "search",
            {
                "query": "任意",
                "k": 5,
                "paths": [
                    f"lore://conversations/channels/{inst_id}/{channel_b}/"
                ],
            },
            conversation_id=channel_a,
        )
        r_legacy = await registry.execute(
            "search",
            {
                "query": "任意",
                "k": 5,
                "paths": [f"conversation://{channel_b}"],
            },
            conversation_id=channel_a,
        )
    mock_search.assert_not_called()
    assert r_lore.get("error") == "out_of_scope"
    assert r_legacy.get("error") == "out_of_scope"


@pytest.mark.asyncio
async def test_search_kb_forged_cursor_expires_without_cross_channel_hits(tmp_path):
    import base64
    import json

    from tests.test_agent_tools import _make_registry

    ci = make_conversation_index(tmp_path)
    store, inst_id, channel_a, channel_b = _channel_pair(tmp_path)
    ci.upsert_message_chunks(
        conversation_id=channel_a,
        message_id="m-a",
        role="user",
        ts="2026-07-14T12:00:00",
        conversation_title="A",
        chunks=[MessageChunk(0, 0, 4, "共享词")],
    )
    ci.upsert_message_chunks(
        conversation_id=channel_b,
        message_id="m-b",
        role="user",
        ts="2026-07-14T12:00:00",
        conversation_title="B",
        chunks=[MessageChunk(0, 0, 4, "共享词")],
    )

    registry, _repo, _idx = _make_registry(
        tmp_path, conversation_index=ci, conversations=store
    )
    forged_filters = {
        "paths": [f"lore://conversations/channels/{inst_id}/{channel_a}/"],
        "kb_prefixes": None,
        "conversation_ids": [channel_b],
    }
    forged = base64.urlsafe_b64encode(
        json.dumps(
            {"q": "共享词", "f": forged_filters, "rev": 0, "off": 0},
            sort_keys=True,
        ).encode()
    ).decode()

    result = await registry.execute(
        "search",
        {
            "query": "共享词",
            "k": 5,
            "paths": [f"lore://conversations/channels/{inst_id}/{channel_a}/"],
            "cursor": forged,
        },
        conversation_id=channel_a,
    )
    assert result.get("cursor_expired") is True
    conv_sources = [s for s in result["sources"] if s["type"] == "conversation"]
    assert conv_sources == []
