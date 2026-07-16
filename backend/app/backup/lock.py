from __future__ import annotations

import threading


class MaintenanceActiveError(Exception):
    """Raised when a second maintenance lock acquire is attempted."""


class MaintenanceLock:
    """Non-reentrant global write lock for import/export maintenance."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = False
        self._reason: str | None = None

    def acquire(self, reason: str) -> None:
        with self._lock:
            if self._active:
                raise MaintenanceActiveError(self._reason or "maintenance")
            self._active = True
            self._reason = reason

    def release(self) -> None:
        with self._lock:
            self._active = False
            self._reason = None

    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def reason(self) -> str | None:
        with self._lock:
            return self._reason
