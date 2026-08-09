"""单工具执行：progress queue bind/drain、cancel、duration。"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable

from app.engine.sandbox.progress import bind_progress_queue, reset_progress_queue
from app.models.llm import ToolCall


class ToolProgressExecutor:
    """在 ToolRegistry.execute 与 loop 调度之间的 progress seam。"""

    def __init__(
        self,
        execute: Callable[..., Awaitable[dict]],
    ) -> None:
        self._execute = execute

    async def stream(
        self,
        tc: ToolCall,
        *,
        active_doc_path: str | None = None,
        conversation_id: str | None = None,
    ) -> AsyncIterator[tuple[str, object]]:
        """Yield ('progress', dict) then ('result', (out, duration_ms))."""
        t0 = time.monotonic()
        queue: asyncio.Queue = asyncio.Queue()
        token = bind_progress_queue(queue)

        async def _run() -> dict:
            try:
                return await self._execute(
                    tc.name,
                    tc.arguments,
                    active_doc_path=active_doc_path,
                    conversation_id=conversation_id,
                )
            except Exception as e:
                return {
                    "summary": f"工具执行失败：{e}",
                    "sources": [],
                    "error": str(e),
                }

        task = asyncio.create_task(_run())
        duration_ms = 0
        out: dict | None = None
        try:
            while True:
                if task.done() and queue.empty():
                    break
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=0.15)
                    yield "progress", item
                except asyncio.TimeoutError:
                    if task.done():
                        while not queue.empty():
                            yield "progress", queue.get_nowait()
                        break
            out = await task
            duration_ms = int((time.monotonic() - t0) * 1000)
        except asyncio.CancelledError:
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
            raise
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
            reset_progress_queue(token)
        assert out is not None
        yield "result", (out, duration_ms)

    async def run(
        self,
        tc: ToolCall,
        *,
        active_doc_path: str | None = None,
        conversation_id: str | None = None,
    ) -> tuple[dict, int]:
        out: dict | None = None
        duration_ms = 0
        async for kind, payload in self.stream(
            tc,
            active_doc_path=active_doc_path,
            conversation_id=conversation_id,
        ):
            if kind == "result":
                out, duration_ms = payload  # type: ignore[misc]
        assert out is not None
        return out, duration_ms
