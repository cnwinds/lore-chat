"""后台 job 日志按游标取尽：``run()`` 与 ``SandboxExecutionEngine`` 共用的唯一输出通道。"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.engine.sandbox.protocol import JobStatus

PollFn = Callable[[int | None], Awaitable[JobStatus]]
ChunkFn = Callable[[str, int | None], None]

_FIRST_POLL_DELAY = 0.02


@dataclass
class DrainOutcome:
    running: bool
    exit_code: int | None
    cursor: int | None


async def drain_job(
    poll: PollFn,
    *,
    cursor: int | None = None,
    deadline: float | None = None,
    on_chunk: ChunkFn | None = None,
    poll_interval_sec: float = 0.2,
) -> DrainOutcome:
    """轮询到命令结束或 ``deadline``（monotonic）。

    每次 poll 先取状态再取日志，所以 ``running=False`` 那次返回的日志已完整。
    有新日志就立即再取；空转时间隔从 20ms 指数退避到 ``poll_interval_sec``。
    """
    delay = min(_FIRST_POLL_DELAY, poll_interval_sec)
    while True:
        status = await poll(cursor)
        if status.next_cursor is not None:
            cursor = status.next_cursor
        if status.logs and on_chunk is not None:
            on_chunk(status.logs, cursor)
        if not status.running:
            return DrainOutcome(running=False, exit_code=status.exit_code, cursor=cursor)
        if deadline is not None and time.monotonic() >= deadline:
            return DrainOutcome(running=True, exit_code=None, cursor=cursor)
        if status.logs:
            # 日志还在分页涌出：立即取下一页，不让大输出被轮询间隔拖成超时
            delay = min(_FIRST_POLL_DELAY, poll_interval_sec)
            continue
        await asyncio.sleep(delay)
        delay = min(delay * 2, poll_interval_sec)


__all__ = ["DrainOutcome", "drain_job"]
