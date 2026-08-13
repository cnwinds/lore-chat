from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.engine.agent.tools import ToolRegistry

ToolHandler = Callable[..., Awaitable[dict] | dict]


def build_tool_dispatch(registry: ToolRegistry) -> dict[str, ToolHandler]:
    """按工具名直挂 tool_impl；对外仍经 ToolRegistry.execute。"""

    kb_read = registry.kb_read
    kb_mutate = registry.kb_mutate
    web = registry.web
    memory = registry.memory
    interaction = registry.interaction
    sandbox = registry.sandbox

    async def _search(args: dict, **kw) -> dict:
        return await asyncio.to_thread(
            kb_read.search_kb, args, conversation_id=kw.get("conversation_id")
        )

    async def _read_doc(args: dict, **kw) -> dict:
        return await asyncio.to_thread(
            kb_read.read_doc, args, conversation_id=kw.get("conversation_id")
        )

    async def _edit_doc(args: dict, **kw) -> dict:
        return await asyncio.to_thread(
            kb_mutate.edit_doc, args, conversation_id=kw.get("conversation_id")
        )

    async def _summarize(args: dict, **kw) -> dict:
        return kb_mutate.summarize_conversation(
            args, conversation_id=kw.get("conversation_id")
        )

    async def _manage_memory(args: dict, **kw) -> dict:
        return await asyncio.to_thread(
            memory.manage_memory, args, conversation_id=kw.get("conversation_id")
        )

    return {
        "search_kb": _search,
        "read_doc": _read_doc,
        "list_kb_structure": lambda args, **kw: asyncio.to_thread(
            kb_read.list_kb_structure, args
        ),
        "read_conversation_context": lambda args, **kw: asyncio.to_thread(
            kb_read.read_conversation_context, args
        ),
        "fetch_url": lambda args, **kw: web.fetch_url(args),
        "web_search": lambda args, **kw: web.web_search(args),
        "generate_image": lambda args, **kw: registry.image_tools.generate_image(args),
        "write_doc": lambda args, **kw: asyncio.to_thread(kb_mutate.write_doc, args),
        "write_kb_file": lambda args, **kw: asyncio.to_thread(
            kb_mutate.write_kb_file, args
        ),
        "edit_doc": _edit_doc,
        "read_doc_meta": lambda args, **kw: asyncio.to_thread(
            kb_mutate.read_doc_meta, args
        ),
        "update_doc_meta": lambda args, **kw: asyncio.to_thread(
            kb_mutate.update_doc_meta, args
        ),
        "summarize_conversation": _summarize,
        "delete_kb": lambda args, **kw: asyncio.to_thread(kb_mutate.delete_kb, args),
        "move_entry": lambda args, **kw: asyncio.to_thread(kb_mutate.move_entry, args),
        "ask_user": lambda args, **kw: interaction.ask_user(args),
        "manage_memory": _manage_memory,
        "recall_memory": lambda args, **kw: asyncio.to_thread(
            memory.recall_memory, args
        ),
        "sandbox_run": lambda args, **kw: sandbox.sandbox_run(args),
        "sandbox_job_status": lambda args, **kw: sandbox.sandbox_job_status(args),
        "sandbox_list_dir": lambda args, **kw: sandbox.sandbox_list_dir(args),
        "sandbox_read_file": lambda args, **kw: sandbox.sandbox_read_file(args),
        "publish_from_sandbox": lambda args, **kw: sandbox.publish_from_sandbox(args),
        "stage_to_sandbox": lambda args, **kw: sandbox.stage_to_sandbox(args),
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
