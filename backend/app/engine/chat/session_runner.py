from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator

from app.engine.agent.events import done, error_event, text_delta, think_delta
from app.engine.agent.prompts import MODE_DEFAULT, MODE_FORCE_WRITE, MODE_NO_WRITE
from app.engine.agent.run_report import AgentRunReport
from app.engine.chat.sse import parse_agent_sse_event
from app.engine.chat.timeline import TimelineAccumulator
from app.logging_config import get_logger

_log = get_logger("chat.session")


class ChatSessionRunner:
    """Agent 运行与 SSE 持久化的 deep module；HTTP 层只做 adapter。"""

    def __init__(self, agent, conversations):
        self.agent = agent
        self.conversations = conversations

    async def stream_ephemeral(
        self,
        text: str,
        *,
        doc_paths: list[str],
        skill_roots: list[str] | None = None,
        primary_doc: str | None,
        web_enabled: bool,
    ) -> AsyncIterator[str]:
        try:
            async for ev in self.agent.run(
                text,
                mode=MODE_DEFAULT,
                active_doc_path=primary_doc,
                active_doc_paths=doc_paths,
                primary_doc_path=primary_doc,
                skill_roots=skill_roots,
                history=None,
                conversation_id=None,
                web_enabled=web_enabled,
            ):
                yield ev
        except Exception as e:
            yield error_event(str(e))

    async def replay_turn(self, turn: dict) -> AsyncIterator[str]:
        assistant = turn.get("assistant_message") or {}
        for block in assistant.get("timeline") or []:
            if block.get("type") == "think" and block.get("content"):
                yield think_delta(block["content"])
            elif block.get("type") == "text" and block.get("content"):
                yield text_delta(block["content"])
        yield done(assistant.get("sources") or [], assistant.get("total_duration_ms") or 0)

    async def stream_and_persist(
        self,
        text: str,
        *,
        conversation_id: str,
        turn: dict,
        history: list[dict],
        doc_paths: list[str],
        skill_roots: list[str] | None = None,
        primary_doc: str | None,
        web_enabled: bool,
    ) -> AsyncIterator[str]:
        acc = TimelineAccumulator()
        assistant_saved = False
        cid = conversation_id
        turn_id = turn["turn_id"]
        run_id = uuid.uuid4().hex[:8]
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

        try:
            async for ev in self.agent.run(
                text,
                mode=MODE_DEFAULT,
                active_doc_path=primary_doc,
                active_doc_paths=doc_paths,
                primary_doc_path=primary_doc,
                skill_roots=skill_roots,
                history=history,
                conversation_id=cid,
                turn_id=turn_id,
                run_id=run_id,
                web_enabled=web_enabled,
            ):
                parsed = parse_agent_sse_event(ev)
                if parsed:
                    acc.accumulate(*parsed)
                    if parsed[0] == "done":
                        done_seen = True
                        stop_reason = "turn_complete"
                        turn_status = "complete"
                        _finalize("complete")
                yield ev
            if not done_seen and stop_reason == "unknown":
                stop_reason = "agent_finished_without_done"
                detail = "agent generator ended without done SSE event"
        except asyncio.CancelledError:
            stop_reason = "client_disconnect"
            turn_status = "interrupted"
            detail = "asyncio.CancelledError (client closed SSE or server shutdown)"

            def _finalize_partial() -> None:
                if acc.timeline or acc.assistant_text:
                    _finalize("interrupted")

            await asyncio.shield(asyncio.to_thread(_finalize_partial))
            raise
        except Exception as e:
            stop_reason = "agent_exception"
            turn_status = "interrupted"
            detail = str(e)
            _finalize("interrupted", error=str(e))
            yield error_event(str(e))
        finally:
            if not assistant_saved and (acc.timeline or acc.assistant_text):
                if stop_reason == "unknown":
                    stop_reason = "stream_closed_partial"
                    detail = "HTTP stream closed with partial assistant output"
                turn_status = turn_status or "interrupted"
                _finalize("interrupted")
            elif not assistant_saved:
                if stop_reason == "unknown":
                    stop_reason = "stream_closed_empty"
                    detail = "HTTP stream closed before any assistant output"

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
                    "client_disconnect",
                    "stream_closed_partial",
                    "stream_closed_empty",
                    "agent_exception",
                    "agent_finished_without_done",
                )
                else logging.INFO
            )
            report.emit(_log, level=level)


def ingest_from_write_kb_result(data: dict) -> dict:
    status = data.get("status")
    rel_path = data.get("rel_path")
    if not rel_path:
        sources = data.get("sources") or []
        rel_path = sources[0]["path"] if sources and sources[0].get("path") else None
    if status is None:
        status = "saved" if rel_path else "rejected"
    return {
        "status": status,
        "rel_path": rel_path,
        "question_id": data.get("question_id"),
        "message": data.get("summary", ""),
    }


async def consume_agent_ingest(agent, text: str) -> dict:
    result: dict | None = None
    async for ev in agent.run(text, mode=MODE_FORCE_WRITE):
        parsed = parse_agent_sse_event(ev)
        if not parsed:
            continue
        event_type, data = parsed
        if event_type == "tool_result" and data.get("tool") == "write_kb":
            result = ingest_from_write_kb_result(data)
    if result is None:
        raise RuntimeError("Agent 未调用 write_kb")
    return result


async def consume_agent_ask(agent, query: str) -> dict:
    text_parts: list[str] = []
    sources: list[dict] = []
    async for ev in agent.run(query, mode=MODE_NO_WRITE):
        parsed = parse_agent_sse_event(ev)
        if not parsed:
            continue
        event_type, data = parsed
        if event_type == "text_delta":
            text_parts.append(data.get("delta", ""))
        elif event_type == "done":
            sources = data.get("sources") or []
    attachments = [
        s["path"]
        for s in sources
        if s.get("type") == "kb" and "/attachments/" in (s.get("path") or "")
    ]
    return {"text": "".join(text_parts), "sources": sources, "attachments": attachments}
