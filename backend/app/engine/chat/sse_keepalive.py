"""SSE 注释心跳：无业务事件时仍向代理写入字节，避免 proxy_read_timeout 掐断长任务。

实现要点：整条上游 AsyncIterator 必须在**同一个** Task 里跑完。
若对 `anext(gen)` 每次新建 Task，会把异步生成器恢复到不同 Context，
导致内部 `ContextVar.reset(token)` 抛错（见 sandbox_progress_queue）。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator


async def with_sse_keepalive(
    source: AsyncIterator[str],
    *,
    interval_sec: float = 20.0,
) -> AsyncIterator[str]:
    """在 source 静默超过 interval_sec 时插入 `: keepalive\\n\\n`（SSE 注释，客户端忽略）。"""
    queue: asyncio.Queue[tuple[str, str | None]] = asyncio.Queue()

    async def _pump() -> None:
        try:
            async for item in source:
                await queue.put(("data", item))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await queue.put(("error", str(e)))
            return
        finally:
            await queue.put(("end", None))

    pump_task = asyncio.create_task(_pump())
    try:
        while True:
            try:
                kind, payload = await asyncio.wait_for(
                    queue.get(), timeout=interval_sec
                )
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            if kind == "data" and payload is not None:
                yield payload
            elif kind == "error":
                raise RuntimeError(payload or "sse source failed")
            else:  # end
                break
    finally:
        if not pump_task.done():
            pump_task.cancel()
            try:
                await pump_task
            except (asyncio.CancelledError, Exception):
                pass
