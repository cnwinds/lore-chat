"""Mid-turn inject broker and tool-loop drain."""

from __future__ import annotations

import pytest

from app.engine.chat.turn_inject import PendingInject, TurnInjectBroker
from app.models.cooldown import CooldownStore


def test_broker_enqueue_requires_active_turn():
    b = TurnInjectBroker()
    with pytest.raises(KeyError):
        b.enqueue(
            "cid",
            PendingInject(
                inject_id="i1",
                text="hi",
                client_message_id="inject:i1",
            ),
        )


def test_broker_drain_fifo():
    b = TurnInjectBroker()
    b.register_turn("cid", "t1")
    b.enqueue(
        "cid",
        PendingInject(inject_id="a", text="one", client_message_id="inject:a"),
    )
    b.enqueue(
        "cid",
        PendingInject(inject_id="b", text="two", client_message_id="inject:b"),
    )
    drained = b.drain("t1")
    assert [x.inject_id for x in drained] == ["a", "b"]
    assert b.drain("t1") == []


def test_unregister_returns_leftovers():
    b = TurnInjectBroker()
    b.register_turn("cid", "t1")
    b.enqueue(
        "cid",
        PendingInject(inject_id="a", text="one", client_message_id="inject:a"),
    )
    left = b.unregister_turn("cid", "t1")
    assert len(left) == 1
    with pytest.raises(KeyError):
        b.enqueue(
            "cid",
            PendingInject(inject_id="b", text="x", client_message_id="inject:b"),
        )


@pytest.mark.asyncio
async def test_tool_loop_applies_inject_after_tools(tmp_path):
    from app.config import Settings
    from app.engine.agent.tool_loop import AgentToolLoop
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

    settings = Settings(kb_path=tmp_path / "knowledge")
    llm = FakeLLMClient(
        tool_responses=[
            {
                "content": None,
                "tool_calls": [
                    ToolCall(id="1", name="search_kb", arguments={"query": "x"}),
                ],
            },
            {"content": "after inject", "tool_calls": []},
        ],
        embed_dim=8,
    )
    repo = KnowledgeRepo(tmp_path / "knowledge")
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    idx = Indexer(vi, fi, llm)
    retr = Retriever(vi, fi, llm)
    pending = PendingStore(tmp_path / "knowledge" / ".kb" / "pending.json")
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
        WebSearch(settings, cooldown=CooldownStore(settings.kb_path / '.kb' / 'search_cd.json')),
        pending,
        writer,
    )
    broker = TurnInjectBroker()
    broker.register_turn("cid", "t1")
    broker.enqueue(
        "cid",
        PendingInject(
            inject_id="inj1",
            text="补充一句",
            client_message_id="inject:inj1",
        ),
    )
    applied: list[str] = []

    def on_applied(item: PendingInject) -> str:
        applied.append(item.inject_id)
        return "msg-1"

    loop = AgentToolLoop(settings, llm, registry)
    events: list[str] = []
    async for ev in loop.stream(
        [{"role": "user", "content": "q"}],
        tools_for_run=[],
        conversation_id="cid",
        active_doc_path=None,
        turn_id="t1",
        run_id="r1",
        inject_broker=broker,
        on_inject_applied=on_applied,
    ):
        if "event: user_inject" in ev:
            events.append("user_inject")
        if "event: inject_deferred" in ev:
            events.append("inject_deferred")
        if "event: done" in ev:
            events.append("done")

    assert events == ["user_inject", "done"]
    assert applied == ["inj1"]


@pytest.mark.asyncio
async def test_tool_loop_defers_inject_without_tools(tmp_path):
    from app.config import Settings
    from app.engine.agent.tool_loop import AgentToolLoop
    from app.engine.agent.tools import ToolRegistry
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
    from tests.helpers import make_writer

    settings = Settings(kb_path=tmp_path / "knowledge")
    llm = FakeLLMClient(
        tool_responses=[{"content": "plain", "tool_calls": []}],
        embed_dim=8,
    )
    repo = KnowledgeRepo(tmp_path / "knowledge")
    vi = VectorIndex(tmp_path / "vec")
    fi = FullTextIndex(tmp_path / "fts.db")
    idx = Indexer(vi, fi, llm)
    retr = Retriever(vi, fi, llm)
    pending = PendingStore(tmp_path / "knowledge" / ".kb" / "pending.json")
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
        WebSearch(settings, cooldown=CooldownStore(settings.kb_path / '.kb' / 'search_cd.json')),
        pending,
        writer,
    )
    broker = TurnInjectBroker()
    broker.register_turn("cid", "t1")
    broker.enqueue(
        "cid",
        PendingInject(
            inject_id="inj2",
            text="补充",
            client_message_id="inject:inj2",
        ),
    )
    loop = AgentToolLoop(settings, llm, registry)
    events: list[str] = []
    async for ev in loop.stream(
        [{"role": "user", "content": "q"}],
        tools_for_run=[],
        conversation_id="cid",
        active_doc_path=None,
        turn_id="t1",
        inject_broker=broker,
    ):
        if "event: user_inject" in ev:
            events.append("user_inject")
        if "event: inject_deferred" in ev:
            events.append("inject_deferred")
        if "event: done" in ev:
            events.append("done")

    assert events == ["inject_deferred", "done"]
