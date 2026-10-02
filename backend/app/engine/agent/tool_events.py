from __future__ import annotations

from app.engine.agent.events import tool_result
from app.engine.chat.tool_query import clip_tool_query
from app.engine.sandbox.result_text import SANDBOX_LOG_TOOLS, display_summary
from app.models.llm import ToolCall

_ASK_KEYS = (
    "question_id",
    "question",
    "options",
    "multi_select",
    "awaiting_user",
    "awaiting_confirm",
)

_COLLAB_KEYS = (
    "room_id",
    "message_id",
    "target_role_id",
    "target_role_name",
    "targets",
    "wake_status",
    "expect_reply",
    "end_turn",
    "hop",
    "error",
    "turn_id",
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
    elif tc.name == "sandbox_stop":
        extra.update(_copy_keys(out, ("workspace_outputs",)))
    elif tc.name == "sandbox_run":
        extra.update(_copy_keys(out, (*_ASK_KEYS, "workspace_outputs")))
        cmd = tc.arguments.get("command")
        if isinstance(cmd, str):
            q = clip_tool_query(cmd)
            if q:
                extra["query"] = q
    elif tc.name in ("search", "web_search"):
        q = tc.arguments.get("query")
        if isinstance(q, str):
            clipped = clip_tool_query(q)
            if clipped:
                extra["query"] = clipped
    elif tc.name == "read":
        parts: list[str] = []
        u = tc.arguments.get("uri")
        if isinstance(u, str) and u.strip():
            parts.append(u.strip())
        raw_uris = tc.arguments.get("uris")
        if isinstance(raw_uris, list):
            for item in raw_uris:
                if isinstance(item, str) and item.strip() and item.strip() not in parts:
                    parts.append(item.strip())
        if parts:
            clipped = clip_tool_query("、".join(parts))
            if clipped:
                extra["query"] = clipped
    elif tc.name == "list":
        qparts: list[str] = []
        u = tc.arguments.get("uri")
        if isinstance(u, str) and u.strip():
            qparts.append(u.strip())
        pat = tc.arguments.get("pattern")
        if isinstance(pat, str) and pat.strip():
            qparts.append(f" · {pat.strip()}")
        typ = tc.arguments.get("type")
        if isinstance(typ, str) and typ.strip():
            qparts.append(f" · type={typ.strip()}")
        if qparts:
            clipped = clip_tool_query("".join(qparts))
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
    elif tc.name == "publish_from_sandbox":
        extra.update(_copy_keys(out, ("attachments", "rel_path")))
    elif tc.name == "write_kb_file":
        extra.update(_copy_keys(out, ("attachments", "rel_path")))
    elif tc.name in (
        "send_message",
        "create_room",
        "create_group",
        "update_group",
        "delete_group",
        "list_rooms",
        "list_groups",
    ):
        extra.update(_copy_keys(out, _COLLAB_KEYS))
    summary = display_summary(out) if tc.name in SANDBOX_LOG_TOOLS else out["summary"]
    return tool_result(
        tc.id,
        tc.name,
        summary,
        out.get("sources"),
        duration_ms,
        content=tool_result_content(tc.name, out),
        **extra,
    )
