"""Turn execution hub: Agent runs as asyncio.Task; SSE subscribers only observe."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from app.engine.agent.events import done, error_event, timeline_state
from app.engine.agent.prompts import MODE_DEFAULT
from app.engine.agent.run_report import AgentRunReport
from app.engine.chat.sse import parse_agent_sse_event
from app.engine.chat.timeline import TimelineAccumulator
from app.engine.chat.turn_inject import PendingInject, TurnInjectBroker
from app.logging_config import get_logger

_log = get_logger("chat.turn_hub")

_END = object()
_RETAIN_FINISHED_SEC = 120.0


@dataclass
class TurnRunSpec:
    text: str
    history: list[dict]
    doc_paths: list[str]
    skill_roots: list[str] | None
    primary_doc: str | None
    web_enabled: bool
    attachments: list[str] | None = None


@dataclass
class ActiveTurn:
    conversation_id: str
    turn_id: str
    run_id: str
    task: asyncio.Task[None] | None = None
    buffer: list[tuple[int, str]] = field(default_factory=list)
    next_seq: int = 0
    subscribers: set[asyncio.Queue] = field(default_factory=set)
    finished: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    retain_until: float = 0.0


class TurnExecutionHub:
    """Owns persisted-turn Agent Tasks independent of any SSE consumer."""

    def __init__(self, agent, conversations, inject_broker: TurnInjectBroker | None = None):
        self.agent = agent
        self.conversations = conversations
        self.inject_broker = inject_broker or TurnInjectBroker()
        self._by_turn: dict[str, ActiveTurn] = {}
        self._cid_to_turn: dict[str, str] = {}

    def get_active(self, conversation_id: str) -> dict[str, Any] | None:
        tid = self._cid_to_turn.get(conversation_id)
        if not tid:
            return None
        at = self._by_turn.get(tid)
        if at is None or at.finished:
            return None
        return {
            "turn_id": at.turn_id,
            "run_id": at.run_id,
            "seq": max(0, at.next_seq - 1),
            "finished": at.finished,
        }

    def resolve_turn_id(self, conversation_id: str) -> str | None:
        """Live or retained-in-memory turn for observation."""
        active = self.get_active(conversation_id)
        if active:
            return active["turn_id"]
        tid = self._cid_to_turn.get(conversation_id)
        if tid and tid in self._by_turn:
            return tid
        for at in self._by_turn.values():
            if at.conversation_id == conversation_id:
                return at.turn_id
        return None

    def ensure_running(
        self,
        conversation_id: str,
        turn: dict,
        spec: TurnRunSpec,
    ) -> ActiveTurn:
        turn_id = turn["turn_id"]
        existing = self._by_turn.get(turn_id)
        if existing is not None and not existing.finished:
            return existing
        if existing is not None and existing.finished:
            # Allow re-observe of retained buffer without restarting.
            return existing

        run_id = uuid.uuid4().hex[:8]
        at = ActiveTurn(
            conversation_id=conversation_id,
            turn_id=turn_id,
            run_id=run_id,
        )
        self._by_turn[turn_id] = at
        self._cid_to_turn[conversation_id] = turn_id
        at.task = asyncio.create_task(
            self._run_turn(at, spec),
            name=f"turn-{conversation_id[:8]}-{turn_id[:8]}",
        )
        return at

    async def subscribe(
        self,
        conversation_id: str,
        turn_id: str,
        *,
        after_seq: int = 0,
    ) -> AsyncIterator[str]:
        at = self._by_turn.get(turn_id)
        if at is None or at.conversation_id != conversation_id:
            return

        q: asyncio.Queue = asyncio.Queue()
        async with at.lock:
            replay = [ev for seq, ev in at.buffer if seq > after_seq]
            finished = at.finished
            if not finished:
                at.subscribers.add(q)

        for ev in replay:
            yield ev
        if finished:
            return

        try:
            while True:
                item = await q.get()
                if item is _END:
                    break
                yield item  # type: ignore[misc]
        except asyncio.CancelledError:
            # Observer disconnected — do not cancel the turn Task.
            raise
        finally:
            at.subscribers.discard(q)

    def request_stop(self, conversation_id: str) -> bool:
        tid = self._cid_to_turn.get(conversation_id)
        if not tid:
            return False
        at = self._by_turn.get(tid)
        if at is None or at.finished or at.task is None:
            return False
        at.task.cancel()
        return True

    def enqueue_inject(self, conversation_id: str, item: PendingInject) -> str:
        return self.inject_broker.enqueue(conversation_id, item)

    def begin_and_ensure(
        self,
        *,
        conversation_id: str,
        user_text: str,
        client_message_id: str,
        observation_allowed: bool,
        doc_context: list | None,
        primary_doc: str | None,
        attachments: list | None,
        doc_paths: list[str],
        skill_roots: list[str] | None,
        web_enabled: bool,
        history: list[dict] | None = None,
    ) -> dict:
        """回合生命周期：begin_turn +（若 running）启动 Task。观测另走 subscribe。"""
        hist = history
        if hist is None:
            hist = self.conversations.llm_history(
                self.conversations.get(conversation_id)
            )
        turn = self.conversations.begin_turn(
            conversation_id,
            user_text=user_text,
            client_message_id=client_message_id,
            observation_allowed=observation_allowed,
            doc_context=doc_context,
            primary_doc=primary_doc,
            attachments=attachments,
        )
        if turn.get("status", "running") == "running":
            self.ensure_running(
                conversation_id,
                turn,
                TurnRunSpec(
                    text=user_text,
                    history=hist,
                    doc_paths=doc_paths,
                    skill_roots=skill_roots,
                    primary_doc=primary_doc,
                    web_enabled=web_enabled,
                    attachments=list(attachments) if attachments else None,
                ),
            )
        return turn

    def recover_orphan_turns(self) -> int:
        """Mark DB running turns with no live Task as interrupted (e.g. after restart)."""
        n = 0
        for row in self.conversations.list_running_turns():
            cid = row["conversation_id"]
            turn_id = row["turn_id"]
            at = self._by_turn.get(turn_id)
            if at is not None and not at.finished and at.task is not None:
                continue
            try:
                self.conversations.finalize_turn(
                    cid,
                    turn_id=turn_id,
                    assistant={
                        "text": "",
                        "timeline": [],
                        "sources": [],
                        "status": "interrupted",
                        "error": "server_restart",
                    },
                )
                n += 1
                _log.warning(
                    "recovered orphan turn cid=%s turn_id=%s",
                    cid,
                    turn_id,
                )
            except Exception:
                _log.exception(
                    "failed to recover orphan turn cid=%s turn_id=%s",
                    cid,
                    turn_id,
                )
        return n

    async def _publish(self, at: ActiveTurn, ev: str) -> None:
        async with at.lock:
            seq = at.next_seq
            at.next_seq += 1
            at.buffer.append((seq, ev))
            subs = list(at.subscribers)
        for q in subs:
            try:
                q.put_nowait(ev)
            except Exception:
                pass

    async def _finish(self, at: ActiveTurn) -> None:
        async with at.lock:
            at.finished = True
            at.retain_until = time.monotonic() + _RETAIN_FINISHED_SEC
            subs = list(at.subscribers)
        for q in subs:
            try:
                q.put_nowait(_END)
            except Exception:
                pass
        if self._cid_to_turn.get(at.conversation_id) == at.turn_id:
            # Keep mapping until retain expires so get_active/stop stay coherent;
            # clear when finished so new turns can start.
            self._cid_to_turn.pop(at.conversation_id, None)

    async def _run_turn(self, at: ActiveTurn, spec: TurnRunSpec) -> None:
        acc = TimelineAccumulator()
        assistant_saved = False
        cid = at.conversation_id
        turn_id = at.turn_id
        run_id = at.run_id
        started = time.monotonic()
        stop_reason = "unknown"
        done_seen = False
        turn_status: str | None = None
        detail: str | None = None

        _log.info(
            "chat run start cid=%s turn_id=%s run_id=%s",
            cid,
            turn_id,
            run_id,
        )

        def _finalize(status: str, error: str | None = None) -> None:
            nonlocal assistant_saved
            if assistant_saved:
                return
            assistant = acc.assistant_payload(status, error=error)
            has_content = bool(
                assistant.get("text")
                or assistant.get("timeline")
                or assistant.get("sources")
                or assistant.get("error")
            )
            if status == "complete" and not has_content:
                _log.warning(
                    "chat empty assistant cid=%s turn_id=%s timeline_blocks=%d text_len=%d",
                    cid,
                    turn_id,
                    len(acc.timeline),
                    len(acc.assistant_text),
                )
            self.conversations.finalize_turn(cid, turn_id=turn_id, assistant=assistant)
            assistant_saved = True

        def _on_inject_applied(item: PendingInject) -> str:
            msg = self.conversations.append_injected_user_message(
                cid,
                text=item.text,
                client_message_id=item.client_message_id,
                doc_context=item.doc_context,
                primary_doc=item.primary_doc,
                attachments=item.attachments,
            )
            return msg["id"]

        self.inject_broker.register_turn(cid, turn_id)
        try:
            async for ev in self.agent.run(
                spec.text,
                mode=MODE_DEFAULT,
                active_doc_path=spec.primary_doc,
                active_doc_paths=spec.doc_paths,
                primary_doc_path=spec.primary_doc,
                skill_roots=spec.skill_roots,
                history=spec.history,
                conversation_id=cid,
                turn_id=turn_id,
                run_id=run_id,
                web_enabled=spec.web_enabled,
                inject_broker=self.inject_broker,
                on_inject_applied=_on_inject_applied,
                attachments=spec.attachments,
            ):
                parsed = parse_agent_sse_event(ev)
                if parsed:
                    acc.accumulate(*parsed)
                    if parsed[0] == "done":
                        done_seen = True
                        stop_reason = "turn_complete"
                        turn_status = "complete"
                        _finalize("complete")
                    # 时间线投影：后端为 source of truth；UI 只 apply
                    if parsed[0] in (
                        "tool_start",
                        "tool_progress",
                        "tool_result",
                        "parallel_batch_start",
                        "parallel_batch_end",
                        "text_delta",
                        "think_delta",
                        "user_inject",
                    ):
                        await self._publish(
                            at,
                            timeline_state(
                                acc.timeline,
                                assistant_text=acc.assistant_text,
                            ),
                        )
                await self._publish(at, ev)
            if not done_seen and stop_reason == "unknown":
                stop_reason = "agent_finished_without_done"
                detail = "agent generator ended without done SSE event"
        except asyncio.CancelledError:
            stop_reason = "explicit_stop"
            turn_status = "interrupted"
            detail = "turn cancelled via stop API or task cancel"

            async def _interrupt_sandbox() -> None:
                try:
                    await self.agent.tools.interrupt_runtime()
                except Exception:
                    _log.warning("interrupt sandbox on stop failed", exc_info=True)

            def _finalize_partial() -> None:
                if acc.timeline or acc.assistant_text:
                    _finalize("interrupted")

            await asyncio.shield(_interrupt_sandbox())
            await asyncio.shield(asyncio.to_thread(_finalize_partial))
            # Do not re-raise: Task is done; observers get END via _finish.
        except Exception as e:
            stop_reason = "agent_exception"
            turn_status = "interrupted"
            detail = str(e)
            _finalize("interrupted", error=str(e))
            await self._publish(at, error_event(str(e)))
        finally:
            self.inject_broker.unregister_turn(cid, turn_id)
            if not assistant_saved and (acc.timeline or acc.assistant_text):
                if stop_reason == "unknown":
                    stop_reason = "stream_closed_partial"
                    detail = "turn ended with partial assistant output"
                turn_status = turn_status or "interrupted"
                _finalize("interrupted")
            elif not assistant_saved:
                if stop_reason == "unknown":
                    stop_reason = "stream_closed_empty"
                    detail = "turn ended before any assistant output"
                # Still finalize empty interrupted so active_turn clears
                if stop_reason in ("explicit_stop", "stream_closed_empty"):
                    _finalize("interrupted")

            report = AgentRunReport(
                layer="chat",
                stop_reason=stop_reason,
                conversation_id=cid,
                turn_id=turn_id,
                run_id=run_id,
                done_emitted=done_seen,
                turn_status=turn_status,
                duration_ms=int((time.monotonic() - started) * 1000),
                detail=detail,
            )
            level = (
                logging.WARNING
                if turn_status == "interrupted"
                or stop_reason
                in (
                    "explicit_stop",
                    "stream_closed_partial",
                    "stream_closed_empty",
                    "agent_exception",
                    "agent_finished_without_done",
                )
                else logging.INFO
            )
            report.emit(_log, level=level)
            await self._finish(at)
