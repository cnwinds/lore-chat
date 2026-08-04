from __future__ import annotations

from app.engine.agent.events import tool_result
from app.models.llm import ToolCall


def tool_result_content(tool: str, out: dict) -> str | None:
    if tool == "fetch_url":
        markdown = out.get("markdown")
        return markdown if markdown else None
    return None


def emit_tool_result_sse(tc: ToolCall, out: dict, duration_ms: int) -> str:
    extra: dict = {}
    if tc.name == "ask_user":
        for key in ("question_id", "question", "options", "multi_select"):
            if key in out:
                extra[key] = out[key]
    elif tc.name in ("search_kb", "web_search"):
        q = tc.arguments.get("query")
        if isinstance(q, str) and q.strip():
            extra["query"] = q.strip()
    elif tc.name == "edit_doc":
        for key in ("preview", "reindex_mode", "applied", "hint", "suggestion"):
            if key in out:
                extra[key] = out[key]
    return tool_result(
        tc.id,
        tc.name,
        out["summary"],
        out.get("sources"),
        duration_ms,
        content=tool_result_content(tc.name, out),
        **extra,
    )
