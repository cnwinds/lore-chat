from __future__ import annotations

from app.engine.memory.observer import MemoryObserver, ObserveResult
from app.engine.memory.store import MemoryStore


class MemoryIntake:
    """自动记忆摄入：对外单一 interface，内部委托 MemoryObserver。"""

    def __init__(self, store: MemoryStore, *, observer: MemoryObserver | None = None):
        self.store = store
        self._observer = observer or MemoryObserver(store)

    @property
    def observer(self) -> MemoryObserver:
        return self._observer

    def observe_user_message(
        self,
        text: str,
        *,
        conversation_id: str,
        message_id: str,
        context_messages: list[dict] | None = None,
    ) -> ObserveResult:
        return self._observer.observe_message(
            text,
            conversation_id=conversation_id,
            message_id=message_id,
            context_messages=context_messages,
        )


__all__ = ["MemoryIntake"]
