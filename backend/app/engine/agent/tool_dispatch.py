from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.engine.agent.tools import ToolRegistry

ToolHandler = Callable[..., Awaitable[dict] | dict]


def build_tool_dispatch(registry: ToolRegistry) -> dict[str, ToolHandler]:
    """按工具名注册 dispatch；对外仍经 ToolRegistry.execute。"""

    async def _search(args: dict, **kw) -> dict:
        return await asyncio.to_thread(
            registry._search_kb, args, conversation_id=kw.get("conversation_id")
        )

    async def _read_doc(args: dict, **kw) -> dict:
        return await asyncio.to_thread(
            registry._read_doc, args, conversation_id=kw.get("conversation_id")
        )

    async def _edit_doc(args: dict, **kw) -> dict:
        return await asyncio.to_thread(
            registry._edit_doc, args, conversation_id=kw.get("conversation_id")
        )

    async def _summarize(args: dict, **kw) -> dict:
        return registry._summarize_conversation(
            args, conversation_id=kw.get("conversation_id")
        )

    async def _manage_memory(args: dict, **kw) -> dict:
        return await asyncio.to_thread(
            registry._manage_memory, args, conversation_id=kw.get("conversation_id")
        )

    return {
        "search_kb": _search,
        "read_doc": _read_doc,
        "list_kb_structure": lambda args, **kw: asyncio.to_thread(
            registry._list_kb_structure, args
        ),
        "read_conversation_context": lambda args, **kw: asyncio.to_thread(
            registry._read_conversation_context, args
        ),
        "fetch_url": lambda args, **kw: registry._fetch_url(args),
        "web_search": lambda args, **kw: registry._web_search(args),
        "write_kb": lambda args, **kw: asyncio.to_thread(registry._write_kb, args),
        "edit_doc": _edit_doc,
        "summarize_conversation": _summarize,
        "delete_kb": lambda args, **kw: asyncio.to_thread(registry._delete_kb, args),
        "move_entry": lambda args, **kw: asyncio.to_thread(registry._move_entry, args),
        "ask_user": lambda args, **kw: registry._ask_user(args),
        "manage_memory": _manage_memory,
        "recall_memory": lambda args, **kw: asyncio.to_thread(registry._recall_memory, args),
        "sandbox_run": lambda args, **kw: registry._sandbox_run(args),
        "sandbox_job_status": lambda args, **kw: registry._sandbox_job_status(args),
        "sandbox_list_dir": lambda args, **kw: registry._sandbox_list_dir(args),
        "sandbox_read_file": lambda args, **kw: registry._sandbox_read_file(args),
        "publish_from_sandbox": lambda args, **kw: registry._publish_from_sandbox(args),
    }


async def dispatch_tool(
    registry: ToolRegistry,
    name: str,
    args: dict,
    *,
    active_doc_path: str | None = None,
    conversation_id: str | None = None,
) -> dict:
    cache = getattr(registry, "_dispatch_handlers", None)
    if cache is None:
        cache = build_tool_dispatch(registry)
        registry._dispatch_handlers = cache
    handler = cache.get(name)
    if handler is None:
        return {
            "summary": f"未知工具：{name}",
            "sources": [],
            "error": f"unknown tool: {name}",
        }
    result = handler(
        args,
        active_doc_path=active_doc_path,
        conversation_id=conversation_id,
    )
    if asyncio.iscoroutine(result):
        return await result
    return result
