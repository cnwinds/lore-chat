from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator

_llm_purpose_var: ContextVar["LlmPurpose | None"] = ContextVar(
    "llm_purpose", default=None
)
_llm_subject_var: ContextVar["LlmCallSubject | None"] = ContextVar(
    "llm_call_subject", default=None
)


@dataclass(frozen=True)
class LlmPurpose:
    purpose: str
    variant: str | None = None
    conversation_id: str | None = None
    scope: str | None = None


@dataclass(frozen=True)
class LlmCallSubject:
    conversation_id: str | None = None
    scope: str | None = None


def current_llm_purpose() -> LlmPurpose | None:
    p = _llm_purpose_var.get()
    if p is None:
        return None
    sub = _llm_subject_var.get()
    if sub is None:
        return p
    return LlmPurpose(
        purpose=p.purpose,
        variant=p.variant,
        conversation_id=p.conversation_id or sub.conversation_id,
        scope=p.scope or sub.scope,
    )


@contextmanager
def llm_purpose(
    purpose: str,
    *,
    variant: str | None = None,
    conversation_id: str | None = None,
    scope: str | None = None,
) -> Iterator[None]:
    token = _llm_purpose_var.set(
        LlmPurpose(
            purpose=purpose,
            variant=variant,
            conversation_id=conversation_id,
            scope=scope,
        )
    )
    try:
        yield
    finally:
        _llm_purpose_var.reset(token)


@contextmanager
def llm_call_subject(
    *,
    conversation_id: str | None = None,
    scope: str | None = None,
) -> Iterator[None]:
    token = _llm_subject_var.set(
        LlmCallSubject(conversation_id=conversation_id, scope=scope)
    )
    try:
        yield
    finally:
        _llm_subject_var.reset(token)
