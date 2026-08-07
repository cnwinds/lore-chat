"""用量调用上下文：由 Agent/会话在调用 LLM 前注入。"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class UsageCallContext:
    conversation_id: str | None = None
    turn_id: str | None = None


_usage_ctx: ContextVar[UsageCallContext | None] = ContextVar(
    "llm_usage_ctx", default=None
)


def get_usage_context() -> UsageCallContext:
    return _usage_ctx.get() or UsageCallContext()


@contextmanager
def usage_context(
    *,
    conversation_id: str | None = None,
    turn_id: str | None = None,
) -> Iterator[None]:
    token = _usage_ctx.set(
        UsageCallContext(conversation_id=conversation_id, turn_id=turn_id)
    )
    try:
        yield
    finally:
        _usage_ctx.reset(token)
