import json

import pytest

from app.config import Settings
from app.engine.agent.orchestrator import AgentOrchestrator
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
    org = Organizer(repo=repo, retriever=retr, indexer=idx, pending=pending, llm=llm)
    fetcher = WebFetcher(settings.fetch_url_timeout, settings.fetch_url_max_bytes)
    web_search = WebSearch(settings)
    registry = ToolRegistry(retr, repo, org, fetcher, web_search, pending)
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
