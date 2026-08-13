from __future__ import annotations

from app.engine.agent.events import tool_result
from app.engine.chat.tool_query import clip_tool_query
from app.models.llm import ToolCall

_ASK_KEYS = (
    "question_id",
    "question",
    "options",
    "multi_select",
    "awaiting_user",
    "awaiting_confirm",
)


def tool_result_content(tool: str, out: dict) -> str | None:
    if tool == "fetch_url":
        markdown = out.get("markdown")
        return markdown if markdown else None
    return None


def _copy_keys(out: dict, keys: tuple[str, ...]) -> dict:
    return {k: out[k] for k in keys if k in out}


def emit_tool_result_sse(tc: ToolCall, out: dict, duration_ms: int) -> str:
    extra: dict = {}
    if tc.name == "ask_user":
        extra.update(_copy_keys(out, _ASK_KEYS))
    elif tc.name == "sandbox_run":
        extra.update(_copy_keys(out, _ASK_KEYS))
        cmd = tc.arguments.get("command")
        if isinstance(cmd, str):
            q = clip_tool_query(cmd)
            if q:
                extra["query"] = q
    elif tc.name in ("search_kb", "web_search"):
        q = tc.arguments.get("query")
        if isinstance(q, str):
            clipped = clip_tool_query(q)
            if clipped:
                extra["query"] = clipped
    elif tc.name == "edit_doc":
        extra.update(
            _copy_keys(out, ("preview", "reindex_mode", "applied", "hint", "suggestion"))
        )
    elif tc.name == "generate_image":
        extra.update(_copy_keys(out, ("attachments", "rel_path", "provider")))
        q = tc.arguments.get("prompt")
        if isinstance(q, str):
            clipped = clip_tool_query(q)
            if clipped:
                extra["query"] = clipped
    return tool_result(
        tc.id,
        tc.name,
        out["summary"],
        out.get("sources"),
        duration_ms,
        content=tool_result_content(tc.name, out),
        **extra,
    )
