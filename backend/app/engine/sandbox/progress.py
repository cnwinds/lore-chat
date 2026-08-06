"""工具执行中的进度上报（供 SSE tool_progress）。"""

from __future__ import annotations

import asyncio
from contextvars import ContextVar, Token
from typing import Any

_progress_queue: ContextVar[asyncio.Queue | None] = ContextVar(
    "sandbox_progress_queue", default=None
)


def bind_progress_queue(queue: asyncio.Queue) -> Token:
    return _progress_queue.set(queue)


def reset_progress_queue(token: Token) -> None:
    try:
        _progress_queue.reset(token)
    except ValueError:
        # Token 与当前 Context 不匹配时（例如生成器曾被错误地跨 Task 恢复）兜底清空
        _progress_queue.set(None)


def emit_progress(message: str, **extra: Any) -> None:
    q = _progress_queue.get()
    if q is None:
        return
    payload = {"message": message, **extra}
    try:
        q.put_nowait(payload)
    except asyncio.QueueFull:
        pass
