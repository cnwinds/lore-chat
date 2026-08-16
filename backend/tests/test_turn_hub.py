"""Turn execution hub: observe disconnect ≠ stop; explicit stop interrupts."""

from __future__ import annotations

import asyncio
import time

import pytest

from app.engine.agent.events import done, text_delta, think_delta, tool_result, tool_start
from app.engine.chat.turn_hub import (
    ActiveTurn,
    TurnExecutionHub,
    TurnRunSpec,
    _RETAIN_FINISHED_SEC,
    _sse_event_name,
)
from app.engine.conversations import ConversationStore


def _cancel_purge(at: ActiveTurn | None) -> None:
    if at is None or at.purge_task is None or at.purge_task.done():
        return
    at.purge_task.cancel()


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
    at = hub._by_turn[turn["turn_id"]]
    await at.task
    _cancel_purge(at)
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
    at = hub._by_turn[turn["turn_id"]]
    await at.task
    _cancel_purge(at)
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
    _cancel_purge(hub._by_turn.get(turn["turn_id"]))


def test_recover_orphan_turns(tmp_path):
    store = ConversationStore(tmp_path / "c")
    cid = store.create()
    turn = store.begin_turn(cid, "hi", "cli-1", observation_allowed=False)
    assert store.get_turn(turn["turn_id"])["status"] == "running"

    hub = TurnExecutionHub(_FakeAgent([]), store)
    n = hub.recover_orphan_turns()
    assert n == 1
    assert store.get_turn(turn["turn_id"])["status"] == "interrupted"


@pytest.mark.asyncio
async def test_think_delta_buffer_stays_linear_with_large_tool_content(tmp_path):
    """Regression: per-delta full timeline_state snapshots caused O(n²) / multi-GB OOM."""
    prior_kb = 200
    n_deltas = 2000
    prior = "X" * (prior_kb * 1024)

    agent = _FakeAgent(
        [
            tool_start("t1", "fetch_url", "fetch", {"url": "https://x"}),
            tool_result("t1", "fetch_url", "ok", content=prior),
            *[think_delta("ab") for _ in range(n_deltas)],
            done([], 1),
        ]
    )
    store = ConversationStore(tmp_path / "c")
    cid = store.create()
    turn = store.begin_turn(cid, "hi", "cli-1", observation_allowed=False)
    hub = TurnExecutionHub(agent, store)
    at = hub.ensure_running(cid, turn, TurnRunSpec("hi", [], [], None, False))
    await at.task

    total = sum(len(ev.encode()) for _, ev in at.buffer)
    # Buggy path ≈ N * prior (~400MB). Fixed path keeps raw deltas + few snapshots.
    assert total < 5_000_000, f"buffer too large: {total} bytes"
    tl_states = sum(1 for _, ev in at.buffer if _sse_event_name(ev) == "timeline_state")
    # tool_start + tool_result both project, but buffer coalesces to the latest only.
    assert tl_states == 1, f"expected coalesced timeline_state, got {tl_states}"
    _cancel_purge(at)


@pytest.mark.asyncio
async def test_finished_turns_purged_after_retain(tmp_path):
    store = ConversationStore(tmp_path / "c")
    cid = store.create()
    turn = store.begin_turn(cid, "hi", "cli-1", observation_allowed=False)
    hub = TurnExecutionHub(_FakeAgent([text_delta("a"), done([], 1)]), store)
    at = hub.ensure_running(cid, turn, TurnRunSpec("hi", [], [], None, False))
    await at.task
    assert turn["turn_id"] in hub._by_turn

    # Expire retain window without waiting wall clock.
    at.retain_until = time.monotonic() - 1
    hub._purge_expired()
    assert turn["turn_id"] not in hub._by_turn
    assert _RETAIN_FINISHED_SEC > 0


@pytest.mark.asyncio
async def test_finish_schedules_purge_without_hub_entry(tmp_path, monkeypatch):
    """Retain expiry must free buffer even if no later subscribe/get_active."""
    monkeypatch.setattr("app.engine.chat.turn_hub._RETAIN_FINISHED_SEC", 0.05)
    store = ConversationStore(tmp_path / "c")
    cid = store.create()
    turn = store.begin_turn(cid, "hi", "cli-1", observation_allowed=False)
    hub = TurnExecutionHub(_FakeAgent([text_delta("a"), done([], 1)]), store)
    tid = turn["turn_id"]
    at = hub.ensure_running(cid, turn, TurnRunSpec("hi", [], [], None, False))
    await at.task
    assert tid in hub._by_turn
    await asyncio.sleep(0.2)
    assert tid not in hub._by_turn
