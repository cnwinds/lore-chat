"""主对话 LLM 请求采集上下文。"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class RequestCaptureContext:
    conversation_id: str
    turn_id: str
    round: int


_capture_ctx: ContextVar[RequestCaptureContext | None] = ContextVar(
    "request_capture_ctx", default=None
)


def get_request_capture_context() -> RequestCaptureContext | None:
    return _capture_ctx.get()


@contextmanager
def request_capture_context(
    *,
    conversation_id: str | None,
    turn_id: str | None,
    round: int,
) -> Iterator[None]:
    if not conversation_id or not turn_id:
        yield
        return
    token = _capture_ctx.set(
        RequestCaptureContext(
            conversation_id=conversation_id,
            turn_id=turn_id,
            round=round,
        )
    )
    try:
        yield
    finally:
        _capture_ctx.reset(token)
