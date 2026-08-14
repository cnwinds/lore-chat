from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager


class MaintenanceActiveError(Exception):
    """Raised when a second maintenance lock acquire is attempted."""


class MaintenanceLock:
    """Non-reentrant global write lock for import/export/reindex.

    ``acquire`` also waits for in-flight background drains (Chroma/sqlite)
    and holds that slot until ``release``, so workers cannot reopen files
    while the knowledge-base directory is being replaced.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = False
        self._reason: str | None = None
        self._drain_lock = threading.Lock()

    def acquire(self, reason: str) -> None:
        with self._lock:
            if self._active:
                raise MaintenanceActiveError(self._reason or "maintenance")
            self._active = True
            self._reason = reason
        self._drain_lock.acquire()

    def release(self) -> None:
        with self._lock:
            self._active = False
            self._reason = None
        try:
            self._drain_lock.release()
        except RuntimeError:
            pass

    def is_active(self) -> bool:
        with self._lock:
            return self._active

    def reason(self) -> str | None:
        with self._lock:
            return self._reason

    @contextmanager
    def try_idle_slot(self) -> Iterator[bool]:
        """Always enter; yield True only if this background batch may run.

        Yields False immediately when import/export/reindex is active, so
        workers do not reopen Chroma/sqlite while the KB directory is replaced.
        """
        if self.is_active():
            yield False
            return
        with self._drain_lock:
            if self.is_active():
                yield False
                return
            yield True
