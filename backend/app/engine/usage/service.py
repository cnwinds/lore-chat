"""用量模块对外 facade（设置 API / 聚合查询）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.engine.usage.store import UsageStore


class UsageService:
    def __init__(self, store: UsageStore):
        self.store = store

    def prefs(self) -> dict[str, Any]:
        return self.store.prefs()

    def update_prefs(self, body: dict[str, Any]) -> dict[str, Any]:
        return self.store.update_prefs(
            timezone_name=body.get("timezone"),
            retention_days=body.get("retention_days"),
        )

    def prices(self) -> list[dict[str, Any]]:
        return self.store.list_prices()

    def upsert_price(self, body: dict[str, Any]) -> dict[str, Any]:
        return self.store.upsert_price(
            body["model"],
            prompt_per_1m=body.get("prompt_per_1m"),
            completion_per_1m=body.get("completion_per_1m"),
            cache_input_per_1m=body.get("cache_input_per_1m"),
            embed_per_1m=body.get("embed_per_1m"),
        )

    def summary(
        self,
        *,
        granularity: str = "day",
        start: str | None = None,
        end: str | None = None,
    ) -> dict[str, Any]:
        start_utc, end_utc = self._resolve_range(start, end)
        self.store.prune()
        return self.store.summarize(
            granularity=granularity, start=start_utc, end=end_utc
        )

    def events(
        self,
        *,
        start: str | None = None,
        end: str | None = None,
        model: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        start_utc, end_utc = self._resolve_range(start, end)
        self.store.prune()
        items = self.store.list_events(
            start=start_utc,
            end=end_utc,
            model=model,
            limit=limit,
            offset=offset,
        )
        return {"items": items, "limit": limit, "offset": offset}

    def clear(self) -> dict[str, Any]:
        n = self.store.clear_all()
        return {"deleted": n}

    def _resolve_range(
        self, start: str | None, end: str | None
    ) -> tuple[str, str]:
        prefs = self.store.prefs()
        tz = ZoneInfo(prefs["timezone"])
        now_local = datetime.now(tz)
        if not start or not end:
            # 默认：本月
            month_start = now_local.replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
            if month_start.month == 12:
                next_month = month_start.replace(year=month_start.year + 1, month=1)
            else:
                next_month = month_start.replace(month=month_start.month + 1)
            start_dt = month_start.astimezone(timezone.utc)
            end_dt = next_month.astimezone(timezone.utc)
            return start_dt.isoformat(), end_dt.isoformat()
        return _as_utc_iso(start), _as_utc_iso(end)


def _as_utc_iso(ts: str) -> str:
    raw = ts.replace("Z", "+00:00")
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()
