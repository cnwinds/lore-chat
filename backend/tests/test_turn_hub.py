"""Turn execution hub: observe disconnect ≠ stop; explicit stop interrupts."""

from __future__ import annotations

import asyncio

import pytest

from app.engine.agent.events import done, text_delta
from app.engine.chat.turn_hub import TurnExecutionHub, TurnRunSpec
from app.engine.conversations import ConversationStore


class _FakeAgent:
    def __init__(self, steps):
        self.steps = steps
        self.tools = type("T", (), {"sandbox": None})()

    async def run(self, *a, **k):
        for step in self.steps:
            if isinstance(step, Exception):
                raise step
            if asyncio.iscoroutine(step):
                await step
                continue
            yield step


@pytest.mark.asyncio
async def test_subscribe_cancel_does_not_stop_turn(tmp_path):
    store = ConversationStore(tmp_path / "c")
    cid = store.create()
    turn = store.begin_turn(cid, "hi", "cli-1", observation_allowed=False)

    started = asyncio.Event()
    release = asyncio.Event()

    async def gate():
        started.set()
        await release.wait()

    agent = _FakeAgent([gate(), text_delta("hello"), done([], 1)])
    hub = TurnExecutionHub(agent, store)

    spec = TurnRunSpec(
        text="hi",
        history=[],
        doc_paths=[],
        skill_catalog=None,
        primary_doc=None,
        web_enabled=False,
    )
    hub.ensure_running(cid, turn, spec)
    await started.wait()

    events: list[str] = []

    async def observe_then_cancel():
        gen = hub.subscribe(cid, turn["turn_id"])
        aiter = gen.__aiter__()
        # Cancel before any event (turn still gated)
        await aiter.aclose()

    await observe_then_cancel()
    assert hub.get_active(cid) is not None
    assert store.get_turn(turn["turn_id"])["status"] == "running"

    release.set()
    await hub._by_turn[turn["turn_id"]].task
    assert store.get_turn(turn["turn_id"])["status"] == "complete"


@pytest.mark.asyncio
async def test_request_stop_finalizes_interrupted(tmp_path):
    store = ConversationStore(tmp_path / "c")
    cid = store.create()
    turn = store.begin_turn(cid, "hi", "cli-1", observation_allowed=False)

    started = asyncio.Event()

    class HangAgent:
        tools = type("T", (), {"sandbox": None})()

        async def run(self, *a, **k):
            yield text_delta("partial")
            started.set()
            await asyncio.sleep(3600)

    hub = TurnExecutionHub(HangAgent(), store)
    hub.ensure_running(
        cid,
        turn,
        TurnRunSpec("hi", [], [], None, False),
    )
    await started.wait()
    assert hub.request_stop(cid) is True
    await hub._by_turn[turn["turn_id"]].task
    assert store.get_turn(turn["turn_id"])["status"] == "interrupted"


@pytest.mark.asyncio
async def test_second_subscribe_replays_buffer(tmp_path):
    store = ConversationStore(tmp_path / "c")
    cid = store.create()
    turn = store.begin_turn(cid, "hi", "cli-1", observation_allowed=False)

    agent = _FakeAgent([text_delta("a"), text_delta("b"), done([], 1)])
    hub = TurnExecutionHub(agent, store)
    hub.ensure_running(
        cid,
        turn,
        TurnRunSpec("hi", [], [], None, False),
    )
    # First subscriber drains to completion
    first = [ev async for ev in hub.subscribe(cid, turn["turn_id"])]
    assert any("text_delta" in ev for ev in first)
    assert any("event: done" in ev for ev in first)

    # Retained buffer still replayable
    second = [ev async for ev in hub.subscribe(cid, turn["turn_id"])]
    assert len(second) >= 2
    assert any("event: done" in ev for ev in second)


def test_recover_orphan_turns(tmp_path):
    store = ConversationStore(tmp_path / "c")
    cid = store.create()
    turn = store.begin_turn(cid, "hi", "cli-1", observation_allowed=False)
    assert store.get_turn(turn["turn_id"])["status"] == "running"

    hub = TurnExecutionHub(_FakeAgent([]), store)
    n = hub.recover_orphan_turns()
    assert n == 1
    assert store.get_turn(turn["turn_id"])["status"] == "interrupted"
