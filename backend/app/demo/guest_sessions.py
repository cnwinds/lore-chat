from __future__ import annotations

import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field

DEFAULT_TTL_SECONDS = 2 * 3600
DEFAULT_CAPACITY = 10000


@dataclass
class _GuestSession:
    expires_at: float
    ip: str | None = None
    message_count: int = field(default=0)


class GuestSessionStore:
    """访客 session：只在进程内，不落盘。重启后访客自动重新签发。"""

    def __init__(
        self,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        capacity: int = DEFAULT_CAPACITY,
    ) -> None:
        self._ttl = ttl_seconds
        self._capacity = max(1, capacity)
        self._lock = threading.Lock()
        self._sessions: OrderedDict[str, _GuestSession] = OrderedDict()

    def create(self, ip: str | None = None) -> str:
        sid = secrets.token_urlsafe(24)
        with self._lock:
            self._sessions[sid] = _GuestSession(
                expires_at=time.monotonic() + self._ttl, ip=ip
            )
            while len(self._sessions) > self._capacity:
                self._sessions.popitem(last=False)
        return sid

    def validate(self, session_id: str | None) -> bool:
        if not session_id:
            return False
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return False
            if entry.expires_at <= time.monotonic():
                self._sessions.pop(session_id, None)
                return False
            return True

    def touch_message(self, session_id: str) -> int:
        with self._lock:
            entry = self._sessions.get(session_id)
            if entry is None:
                return 0
            entry.message_count += 1
            return entry.message_count

    def message_count(self, session_id: str) -> int:
        with self._lock:
            entry = self._sessions.get(session_id)
            return entry.message_count if entry else 0
