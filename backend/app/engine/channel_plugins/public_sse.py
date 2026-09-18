"""脚本通道精简 SSE：把内部 Agent 事件投影成对外契约。HTTP 不解析 SSE。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from app.engine.agent.events import sse_event
from app.engine.channel_plugins.group_policy import format_needs_input
from app.engine.chat.sse import parse_agent_sse_event

_THINK_EVENTS = frozenset({"think_delta"})
_TOOL_EVENTS = frozenset({"tool_start", "tool_progress", "tool_result"})
_QUERY_KEYS = ("query", "prompt", "command", "path", "sandbox_path")
_CONTENT_LIMIT = 4000
_QUERY_LIMIT = 500


def _clip(text: str, limit: int) -> str:
    body = (text or "").strip()
    if len(body) <= limit:
        return body
    return body[: max(0, limit - 1)].rstrip() + "…"


def _tool_query(data: dict[str, Any]) -> str | None:
    raw = data.get("query")
    if isinstance(raw, str) and raw.strip():
        return _clip(raw, _QUERY_LIMIT)
    inp = data.get("input")
    if isinstance(inp, dict):
        for key in _QUERY_KEYS:
            value = inp.get(key)
            if isinstance(value, str) and value.strip():
                return _clip(value, _QUERY_LIMIT)
    return None


def _public_tool_payload(event_type: str, data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ("id", "tool", "label", "ts", "status", "duration_ms", "error"):
        if data.get(key) is not None:
            out[key] = data[key]
    query = _tool_query(data)
    if query:
        out["query"] = query
    if event_type == "tool_progress":
        out["message"] = data.get("message") or ""
    if event_type == "tool_result":
        summary = data.get("summary")
        if summary:
            out["summary"] = summary
        content = data.get("content")
        if isinstance(content, str) and content.strip():
            out["content"] = _clip(content, _CONTENT_LIMIT)
        if data.get("question"):
            out["question"] = data["question"]
        if data.get("options") is not None:
            out["options"] = data["options"]
    return out


def project_agent_event(
    raw: str,
    *,
    show_thinking: bool = False,
    show_tool_output: bool = False,
) -> str | None:
    parsed = parse_agent_sse_event(raw)
    if not parsed:
        return None
    event_type, data = parsed
    if event_type in _THINK_EVENTS:
        if not show_thinking:
            return None
        return sse_event("think_delta", {"delta": data.get("delta") or ""})
    if event_type in _TOOL_EVENTS:
        if not show_tool_output:
            return None
        return sse_event(event_type, _public_tool_payload(event_type, data))
    if event_type == "text_delta":
        return sse_event("text_delta", {"delta": data.get("delta") or ""})
    if event_type == "error":
        return sse_event("error", {"message": data.get("message") or ""})
    return None


def public_start_event(conversation_id: str, turn_id: str) -> str:
    return sse_event(
        "start",
        {
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "status": "running",
        },
    )


def public_done_event(
    payload: dict[str, Any],
    *,
    agent_done: dict[str, Any] | None = None,
) -> str:
    assistant = payload.get("assistant") or {}
    data: dict[str, Any] = {
        "conversation_id": payload.get("conversation_id"),
        "turn_id": payload.get("turn_id"),
        "status": payload.get("status") or "completed",
        "message": payload.get("message"),
    }
    sources = assistant.get("sources") or (agent_done or {}).get("sources") or []
    if sources:
        data["sources"] = sources
    duration = assistant.get("total_duration_ms")
    if duration is None and agent_done:
        duration = agent_done.get("total_duration_ms")
    if duration is not None:
        data["total_duration_ms"] = duration
    needs = format_needs_input(assistant)
    if needs:
        data["needs_input"] = needs
    return sse_event("done", data)


async def iter_public_chat_sse(
    source: AsyncIterator[str],
    *,
    conversation_id: str,
    turn_id: str,
    show_thinking: bool = False,
    show_tool_output: bool = False,
    done_payload: Callable[[], dict[str, Any]],
) -> AsyncIterator[str]:
    yield public_start_event(conversation_id, turn_id)
    agent_done: dict[str, Any] | None = None
    async for raw in source:
        parsed = parse_agent_sse_event(raw)
        if parsed and parsed[0] == "done":
            agent_done = parsed[1]
            continue
        projected = project_agent_event(
            raw,
            show_thinking=show_thinking,
            show_tool_output=show_tool_output,
        )
        if projected:
            yield projected
    yield public_done_event(done_payload(), agent_done=agent_done)
