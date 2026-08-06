"""Running-turn mid-stream user injects (A1): queue until after tool results."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class PendingInject:
    inject_id: str
    text: str
    client_message_id: str
    doc_context: list | None = None
    primary_doc: str | None = None
    attachments: list[str] | None = None


@dataclass
class TurnInjectBroker:
    """In-memory pending injects keyed by active turn."""

    _lock: threading.Lock = field(default_factory=threading.Lock)
    _by_turn: dict[str, list[PendingInject]] = field(default_factory=dict)
    _cid_to_turn: dict[str, str] = field(default_factory=dict)

    def register_turn(self, conversation_id: str, turn_id: str) -> None:
        with self._lock:
            prev = self._cid_to_turn.get(conversation_id)
            if prev and prev != turn_id:
                self._by_turn.pop(prev, None)
            self._cid_to_turn[conversation_id] = turn_id
            self._by_turn.setdefault(turn_id, [])

    def unregister_turn(self, conversation_id: str, turn_id: str) -> list[PendingInject]:
        with self._lock:
            if self._cid_to_turn.get(conversation_id) == turn_id:
                del self._cid_to_turn[conversation_id]
            return self._by_turn.pop(turn_id, [])

    def enqueue(self, conversation_id: str, item: PendingInject) -> str:
        """Return 'queued' or raise KeyError if no active turn."""
        with self._lock:
            turn_id = self._cid_to_turn.get(conversation_id)
            if not turn_id or turn_id not in self._by_turn:
                raise KeyError("no_active_turn")
            self._by_turn[turn_id].append(item)
            return "queued"

    def drain(self, turn_id: str) -> list[PendingInject]:
        with self._lock:
            items = self._by_turn.get(turn_id) or []
            self._by_turn[turn_id] = []
            return items
