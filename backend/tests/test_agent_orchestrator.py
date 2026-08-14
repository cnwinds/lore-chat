import json

import pytest

from app.config import Settings
from app.models.cooldown import CooldownStore
from app.engine.agent.orchestrator import AgentOrchestrator
from app.engine.source_key import extend_sources, source_dedupe_key
from app.engine.agent.tools import ToolRegistry
from app.engine.organizer import Organizer
from app.engine.pending import PendingStore
from app.engine.retriever import Retriever
from app.engine.web.fetcher import WebFetcher
from app.engine.web.search import WebSearch
from app.index.fulltext import FullTextIndex
from app.index.indexer import Indexer
from app.index.vector import VectorIndex
from app.models.llm import FakeLLMClient, ToolCall
from app.storage.repo import KnowledgeRepo
from tests.helpers import make_writer


def _make_orchestrator(tmp_path, tool_responses, *, agent_parallel_tools=True):
    kb = tmp_path / "knowledge"
    settings = Settings(kb_path=kb, agent_parallel_tools=agent_parallel_tools)
    llm = FakeLLMClient(tool_responses=tool_responses, embed_dim=8)
    repo = KnowledgeRepo(kb)
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    idx = Indexer(vi, fi, llm)
    retr = Retriever(vi, fi, llm)
    pending = PendingStore(kb / ".kb" / "pending.json")
    writer = make_writer(repo, tmp_path)
    org = Organizer(
        repo=repo,
        retriever=retr,
        pending=pending,
        llm=llm,
        knowledge_writer=writer,
    )
    fetcher = WebFetcher(settings.fetch_url_timeout, settings.fetch_url_max_bytes)
    web_search = WebSearch(settings, cooldown=CooldownStore(settings.kb_path / '.kb' / 'search_cd.json'))
    registry = ToolRegistry(
        retr, repo, org, fetcher, web_search, pending, writer
    )
    return AgentOrchestrator(settings, llm, registry)


def _parse_event_types(events: list[str]) -> list[str]:
    types = []
    for ev in events:
        if ev.startswith("event: "):
            types.append(ev.split("\n")[0].replace("event: ", ""))
    return types


def _assert_events_have_ts(events: list[str]) -> None:
    for ev in events:
        if not ev.startswith("event: "):
            continue
        data_line = next(l for l in ev.split("\n") if l.startswith("data: "))
        data = json.loads(data_line.replace("data: ", ""))
        assert "ts" in data


def test_source_key_conversation_includes_message_and_char_range():
    a = {"type": "conversation", "cid": "c1", "message_id": "m1", "start_char": 0, "end_char": 4}
    b = {"type": "conversation", "cid": "c1", "message_id": "m2", "start_char": 0, "end_char": 4}
    c = {"type": "conversation", "cid": "c1", "message_id": "m1", "start_char": 4, "end_char": 8}
    assert source_dedupe_key(a) != source_dedupe_key(b)
    assert source_dedupe_key(a) != source_dedupe_key(c)
    assert source_dedupe_key(a) == source_dedupe_key(dict(a))


def test_extend_sources_keeps_distinct_conversation_hits():
    all_sources: list[dict] = []
    extend_sources(
        all_sources,
        [
            {"type": "conversation", "cid": "c1", "message_id": "m1", "start_char": 0, "end_char": 4},
            {"type": "conversation", "cid": "c1", "message_id": "m2", "start_char": 0, "end_char": 4},
        ],
    )
    assert len(all_sources) == 2
    # 重复的同一片段命中会被去重
    extend_sources(
        all_sources,
        [{"type": "conversation", "cid": "c1", "message_id": "m1", "start_char": 0, "end_char": 4}],
    )
    assert len(all_sources) == 2


@pytest.mark.asyncio
async def test_orchestrator_emits_timeline_events(tmp_path):
    orchestrator = _make_orchestrator(
        tmp_path,
        tool_responses=[
            {
                "content": None,
                "tool_calls": [ToolCall(id="1", name="search_kb", arguments={"query": "test"})],
            },
            {"content": "答案是 Y", "tool_calls": []},
        ],
    )
    events = []
    async for ev in orchestrator.run("问题", mode="no_write"):
        events.append(ev)

    event_types = _parse_event_types(events)
    assert "tool_start" in event_types
    assert "tool_result" in event_types
    assert "text_delta" in event_types
    assert "done" in event_types
    _assert_events_have_ts(events)


@pytest.mark.asyncio
async def test_orchestrator_tool_result_includes_search_query(tmp_path):
    orchestrator = _make_orchestrator(
        tmp_path,
        tool_responses=[
            {
                "content": None,
                "tool_calls": [
                    ToolCall(id="1", name="search_kb", arguments={"query": "docker 日志"}),
                ],
            },
            {"content": "结论", "tool_calls": []},
        ],
    )
    events = []
    async for ev in orchestrator.run("问题", mode="no_write"):
        events.append(ev)

    tool_result_data = None
    for ev in events:
        if ev.startswith("event: tool_result\n"):
            tool_result_data = json.loads(ev.split("data: ", 1)[1].strip())
            break
    assert tool_result_data is not None
    assert tool_result_data["query"] == "docker 日志"


@pytest.mark.asyncio
async def test_orchestrator_passes_conversation_history(tmp_path):
    orchestrator = _make_orchestrator(
        tmp_path,
        tool_responses=[{"content": "好的", "tool_calls": []}],
    )
    history = [
        {"role": "user", "content": "Claude Opus 是什么"},
        {"role": "assistant", "content": "Opus 是 Anthropic 的旗舰模型。"},
    ]
    async for _ in orchestrator.run("那 4.8 呢？", history=history):
        pass

    llm = orchestrator.llm
    assert llm.calls
    messages = llm.calls[-1]["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1:3] == history
    assert messages[-1] == {"role": "user", "content": "那 4.8 呢？"}


@pytest.mark.asyncio
async def test_orchestrator_parallel_batch(tmp_path):
    orchestrator = _make_orchestrator(
        tmp_path,
        tool_responses=[
            {
                "content": None,
                "tool_calls": [
                    ToolCall(id="1", name="search_kb", arguments={"query": "a"}),
                    ToolCall(id="2", name="read_doc", arguments={"path": "missing.md"}),
                ],
            },
            {"content": "综合结论", "tool_calls": []},
        ],
        agent_parallel_tools=True,
    )
    events = []
    async for ev in orchestrator.run("并行检索", mode="no_write"):
        events.append(ev)

    event_types = _parse_event_types(events)
    assert "parallel_batch_start" in event_types
    assert "parallel_batch_end" in event_types
    assert event_types.count("tool_start") == 2
    assert event_types.count("tool_result") == 2
    _assert_events_have_ts(events)


@pytest.mark.asyncio
async def test_orchestrator_parallel_generate_image(tmp_path):
    """同轮多个 generate_image 应并行，并透出 tool_progress。"""
    import asyncio
    import time
    from unittest.mock import MagicMock

    from app.engine.progress import emit_progress

    orchestrator = _make_orchestrator(
        tmp_path,
        tool_responses=[
            {
                "content": None,
                "tool_calls": [
                    ToolCall(id="g1", name="generate_image", arguments={"prompt": "logo-a"}),
                    ToolCall(id="g2", name="generate_image", arguments={"prompt": "logo-b"}),
                ],
            },
            {"content": "两张都好了", "tool_calls": []},
        ],
        agent_parallel_tools=True,
    )
    mock_gen = MagicMock()
    mock_gen.configured = True
    orchestrator.tools.image_tools.image_gen = mock_gen

    started: list[float] = []

    async def fake_gen(args):
        started.append(time.monotonic())
        emit_progress(f"生图中…{args.get('prompt')}")
        await asyncio.sleep(0.2)
        prompt = args.get("prompt")
        return {
            "summary": f"已生成 {prompt}",
            "sources": [{"type": "kb", "path": f"媒体/生成/{prompt}.png"}],
            "attachments": [f"媒体/生成/{prompt}.png"],
            "rel_path": f"媒体/生成/{prompt}.png",
            "provider": "openai",
        }

    orchestrator.tools.image_tools.generate_image = fake_gen

    events: list[str] = []
    t0 = time.monotonic()
    async for ev in orchestrator.run("出两张 logo", mode="default"):
        events.append(ev)
    wall = time.monotonic() - t0

    event_types = _parse_event_types(events)
    assert "parallel_batch_start" in event_types
    assert "parallel_batch_end" in event_types
    assert event_types.count("tool_start") == 2
    assert event_types.count("tool_result") == 2
    assert "tool_progress" in event_types
    # 并行：两任务几乎同时开始，墙钟应明显小于串行 0.4s
    assert len(started) == 2
    assert abs(started[0] - started[1]) < 0.15
    assert wall < 0.55
    _assert_events_have_ts(events)


@pytest.mark.asyncio
async def test_orchestrator_stream_does_not_block_event_loop(tmp_path):
    """同步 LLM 流式迭代不得堵死事件循环（否则聊天中 /api/doc 会一直加载中）。"""
    import asyncio
    import time

    from app.models.llm import ChatStreamChunk, ChatWithToolsResult

    orchestrator = _make_orchestrator(
        tmp_path,
        tool_responses=[{"content": "ok", "tool_calls": []}],
    )

    class SlowStreamLLM(FakeLLMClient):
        def stream_chat_with_tools(self, messages, tools, *, big=True, temperature=0.2):
            self.calls.append({"messages": messages, "big": big, "tools": tools})
            time.sleep(0.25)
            yield ChatStreamChunk(text_delta="ok")
            yield ChatStreamChunk(
                result=ChatWithToolsResult(content="ok", tool_calls=[])
            )

    orchestrator.llm = SlowStreamLLM(tool_responses=[], embed_dim=8)

    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.05)
            ticks += 1

    task = asyncio.create_task(ticker())
    try:
        async for _ in orchestrator.run("ping"):
            pass
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert ticks >= 3, f"event loop stalled during sync LLM stream (ticks={ticks})"


def _tool_names_from_defs(defs):
    return {d["function"]["name"] for d in defs}


@pytest.mark.asyncio
async def test_run_web_disabled_excludes_web_search(tmp_path):
    orchestrator = _make_orchestrator(
        tmp_path,
        tool_responses=[{"content": "ok", "tool_calls": []}],
    )
    async for _ in orchestrator.run("你好", web_enabled=False):
        pass

    tools = orchestrator.llm.calls[-1]["tools"]
    names = _tool_names_from_defs(tools)
    assert "web_search" not in names
    assert "fetch_url" in names


@pytest.mark.asyncio
async def test_run_injects_skill_catalog(tmp_path):
    kb = tmp_path / "knowledge"
    repo = KnowledgeRepo(kb)
    repo.write_doc(
        "技能/demo/SKILL.md",
        {"title": "Demo"},
        "---\nname: demo-skill\ndescription: Use when testing catalog injection.\n---\n\n"
        "ROLE RULE: speak like demo.\n",
        commit_msg="seed",
    )
    orchestrator = _make_orchestrator(
        tmp_path,
        tool_responses=[{"content": "ok", "tool_calls": []}],
    )
    catalog = [
        {
            "root": "技能/demo",
            "name": "demo-skill",
            "description": "Use when testing catalog injection.",
            "entry": "技能/demo/SKILL.md",
        }
    ]
    async for _ in orchestrator.run("你好", skill_catalog=catalog):
        pass
    messages = orchestrator.llm.calls[-1]["messages"]
    system_contents = "\n".join(
        m["content"] for m in messages if m["role"] == "system"
    )
    assert "Skill 目录" in system_contents
    assert "demo-skill" in system_contents
    assert "Use when testing catalog injection." in system_contents
    assert "技能/demo/SKILL.md" in system_contents
    assert "ROLE RULE" not in system_contents


@pytest.mark.asyncio
async def test_run_injects_multi_skill_conflict_rules(tmp_path):
    orchestrator = _make_orchestrator(
        tmp_path,
        tool_responses=[{"content": "ok", "tool_calls": []}],
    )
    catalog = [
        {
            "root": "技能/a",
            "name": "skill-a",
            "description": "Use a.",
            "entry": "技能/a/SKILL.md",
        },
        {
            "root": "技能/b",
            "name": "skill-b",
            "description": "Use b.",
            "entry": "技能/b/SKILL.md",
        },
    ]
    async for _ in orchestrator.run("你好", skill_catalog=catalog):
        pass
    system_contents = "\n".join(
        m["content"]
        for m in orchestrator.llm.calls[-1]["messages"]
        if m["role"] == "system"
    )
    assert "Skill 冲突总则" in system_contents


@pytest.mark.asyncio
async def test_run_injects_multi_doc_context(tmp_path):
    orchestrator = _make_orchestrator(
        tmp_path,
        tool_responses=[{"content": "ok", "tool_calls": []}],
    )
    async for _ in orchestrator.run(
        "合并",
        active_doc_paths=["a.md", "b.md"],
        primary_doc_path="a.md",
    ):
        pass
    messages = orchestrator.llm.calls[-1]["messages"]
    system_contents = "\n".join(
        m["content"] for m in messages if m["role"] == "system"
    )
    assert "a.md" in system_contents
    assert "b.md" in system_contents
    assert "主文档" in system_contents or "默认编辑" in system_contents


@pytest.mark.asyncio
async def test_run_no_write_excludes_write_doc(tmp_path):
    orchestrator = _make_orchestrator(
        tmp_path,
        tool_responses=[{"content": "ok", "tool_calls": []}],
    )
    async for _ in orchestrator.run("问题", mode="no_write", web_enabled=True):
        pass

    tools = orchestrator.llm.calls[-1]["tools"]
    names = _tool_names_from_defs(tools)
    assert "write_doc" not in names


@pytest.mark.asyncio
async def test_run_includes_generate_image_when_image_tools_configured(tmp_path):
    """回归：须读 tools.image_tools（不是不存在的 tools.image）。"""
    from unittest.mock import MagicMock

    orchestrator = _make_orchestrator(
        tmp_path,
        tool_responses=[{"content": "ok", "tool_calls": []}],
    )
    mock_gen = MagicMock()
    mock_gen.configured = True
    orchestrator.tools.image_tools.image_gen = mock_gen

    async for _ in orchestrator.run("画一只猫", mode="default", web_enabled=True):
        pass

    names = _tool_names_from_defs(orchestrator.llm.calls[-1]["tools"])
    assert "generate_image" in names
