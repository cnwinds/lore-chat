from __future__ import annotations
import json

from app.time import now_iso_seconds


def now_ts() -> str:
    return now_iso_seconds()

def sse_event(event_type: str, data: dict) -> str:
    if "ts" not in data:
        data = {**data, "ts": now_ts()}
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

def tool_start(id, tool, label, input_data):
    return sse_event("tool_start", {"id": id, "tool": tool, "label": label, "input": input_data})

def tool_result(
    id,
    tool,
    summary,
    sources=None,
    duration_ms=None,
    ts=None,
    content=None,
    **extra,
):
    payload = {"id": id, "tool": tool, "summary": summary, "sources": sources or []}
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms
    if ts:
        payload["ts"] = ts
    if content:
        payload["content"] = content
    payload.update(extra)
    return sse_event("tool_result", payload)

def parallel_batch_start(batch_id, tools):
    return sse_event("parallel_batch_start", {"batch_id": batch_id, "tools": tools})

def parallel_batch_end(batch_id, duration_ms):
    return sse_event("parallel_batch_end", {"batch_id": batch_id, "duration_ms": duration_ms})

def text_delta(delta):
    return sse_event("text_delta", {"delta": delta})

def think_delta(delta):
    return sse_event("think_delta", {"delta": delta})

def done(sources, total_duration_ms):
    return sse_event("done", {"sources": sources, "total_duration_ms": total_duration_ms})

def error_event(message):
    return sse_event("error", {"message": message})
