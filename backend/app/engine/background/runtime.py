from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from app.config import Settings

_WORKER_META: dict[str, dict[str, Any]] = {
    "derivation-worker": {
        "label": "索引与记忆派生",
        "interval_seconds": 0.5,
    },
    "card-maintenance": {
        "label": "卡片维护",
        "interval_seconds": 3600.0,
    },
    "memory-maintenance": {
        "label": "主人记忆衰减",
        "interval_seconds": None,
    },
    "role-schedule-worker": {
        "label": "角色定时任务",
        "interval_seconds": 30.0,
    },
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BackgroundRuntime:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._workers: dict[str, dict[str, Any]] = {}

    @staticmethod
    def paused(settings: Settings) -> frozenset[str]:
        return frozenset(settings.background_paused)

    def mark_running(self, name: str) -> None:
        with self._lock:
            w = self._workers.setdefault(name, {})
            w["running"] = True
            w["last_run_at"] = _utc_now()

    def record_tick(
        self,
        name: str,
        *,
        result: Any = None,
        error: str | None = None,
        skipped: str | None = None,
    ) -> None:
        with self._lock:
            w = self._workers.setdefault(name, {})
            w["running"] = False
            w["last_run_at"] = w.get("last_run_at") or _utc_now()
            if skipped:
                w["last_result"] = {"skipped": skipped}
            elif error:
                w["last_error"] = error
                w["last_error_at"] = _utc_now()
                w["last_result"] = None
            else:
                w["last_error"] = None
                w["last_error_at"] = None
                if result is not None:
                    w["last_result"] = result
                    if _tick_had_activity(result):
                        w["last_active_at"] = _utc_now()

    def worker_status(
        self, settings: Settings, *, memory_interval_seconds: float
    ) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        with self._lock:
            for name, meta in _WORKER_META.items():
                w = dict(self._workers.get(name) or {})
                interval = meta["interval_seconds"]
                if name == "memory-maintenance":
                    interval = memory_interval_seconds
                out[name] = {
                    "name": name,
                    "label": meta["label"],
                    "interval_seconds": float(interval or 0),
                    "running": bool(w.get("running")),
                    "last_run_at": w.get("last_run_at"),
                    "last_active_at": w.get("last_active_at"),
                    "last_result": w.get("last_result"),
                    "last_error": w.get("last_error"),
                    "last_error_at": w.get("last_error_at"),
                }
        return out


def _tick_had_activity(result: Any) -> bool:
    if not isinstance(result, dict):
        return bool(result)
    for key in ("derivation", "session_observe", "embedded", "faded", "ops_applied"):
        if key in result:
            val = result[key]
            if val == "paused":
                continue
            try:
                if int(val) > 0:
                    return True
            except (TypeError, ValueError):
                pass
    for key in ("consolidated_scopes", "evolved_scopes"):
        val = result.get(key)
        try:
            if int(val or 0) > 0:
                return True
        except (TypeError, ValueError):
            pass
    return False
