from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

_HOUR = 3600.0
_DAY = 86400.0

GUEST_MAX_INPUT_CHARS = 2000
GUEST_MAX_TOOL_CALLS = 10


class DemoQuotaExceeded(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class DemoQuota:
    """演示站成本闸门：全部计数在进程内，重启即清零。"""

    def __init__(
        self,
        per_session: int = 20,
        per_ip_hourly: int = 60,
        daily_total: int = 2000,
        max_concurrent: int = 10,
    ) -> None:
        self._per_session = per_session
        self._per_ip_hourly = per_ip_hourly
        self._daily_total = daily_total
        self._max_concurrent = max_concurrent
        self._lock = threading.Lock()
        self._session_counts: dict[str, int] = defaultdict(int)
        self._ip_hits: dict[str, deque[float]] = defaultdict(deque)
        self._day_hits: deque[float] = deque()
        self._in_flight = 0

    def acquire(self, session_id: str, ip: str | None) -> None:
        now = time.monotonic()
        with self._lock:
            if self._in_flight >= self._max_concurrent:
                raise DemoQuotaExceeded("demo_busy", "演示站正忙，请稍后再试")
            if self._session_counts[session_id] >= self._per_session:
                raise DemoQuotaExceeded(
                    "demo_quota_exceeded", "本次演示的提问额度已用完"
                )
            if ip:
                hits = self._ip_hits[ip]
                while hits and now - hits[0] > _HOUR:
                    hits.popleft()
                if len(hits) >= self._per_ip_hourly:
                    raise DemoQuotaExceeded(
                        "demo_quota_exceeded", "本小时的提问额度已用完"
                    )
            while self._day_hits and now - self._day_hits[0] > _DAY:
                self._day_hits.popleft()
            if len(self._day_hits) >= self._daily_total:
                raise DemoQuotaExceeded(
                    "demo_quota_exceeded", "今天的演示额度已用完"
                )

            self._session_counts[session_id] += 1
            if ip:
                self._ip_hits[ip].append(now)
            self._day_hits.append(now)
            self._in_flight += 1

    def release(self) -> None:
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)
