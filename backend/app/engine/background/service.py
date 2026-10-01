"""后台流程概览：组合 catalog、运行状态、积压与用量。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import Settings
from app.engine.background.call_log import BackgroundCallLog
from app.engine.background.catalog import (
    ALL_PURPOSE_KEYS,
    build_catalog_static,
    chain_summaries,
    setting_meta,
)
from app.engine.background.runtime import BackgroundRuntime
from app.engine.conversations import ConversationStore
from app.engine.usage.store import UsageStore
from app.index.partitioned.search_index import SearchIndex


class BackgroundOverviewService:
    def __init__(
        self,
        *,
        settings: Settings,
        runtime: BackgroundRuntime,
        call_log: BackgroundCallLog,
        usage_store: UsageStore,
        conversations: ConversationStore,
        search_index: SearchIndex | None,
    ):
        self.settings = settings
        self.runtime = runtime
        self.call_log = call_log
        self.usage_store = usage_store
        self.conversations = conversations
        self.search_index = search_index

    def status(self) -> dict[str, Any]:
        return self._build_status(include_catalog=False)

    def overview(self) -> dict[str, Any]:
        static = build_catalog_static(self.settings)
        st = self._build_status(include_catalog=True)
        return {
            "generated_at": st["generated_at"],
            "groups": static["groups"],
            "lanes": static["lanes"],
            "nodes": static["nodes"],
            "settings": setting_meta(self.settings),
            "chains": chain_summaries(self.settings),
            "pausable": static["pausable"],
            "status": st,
        }

    def _build_status(self, *, include_catalog: bool) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        generated_at = now.isoformat()
        settings = self.settings
        mem_hours = float(getattr(settings, "memory_maintenance_interval_hours", 24) or 24)
        mem_hours = max(1.0, mem_hours)
        workers = self.runtime.worker_status(
            settings, memory_interval_seconds=mem_hours * 3600.0
        )
        backlog = self._backlog()
        stats = self._purpose_stats(now)
        totals = self._totals_24h(now, stats)
        return {
            "generated_at": generated_at,
            "paused": list(BackgroundRuntime.paused(settings)),
            "workers": workers,
            "backlog": backlog,
            "stats": stats,
            "totals_24h": totals,
        }

    def _backlog(self) -> dict[str, Any]:
        pending = 0
        dirty = 0
        embed_pending: int | None = None
        try:
            pending = self.conversations.count_outbox_pending("session_observe_memory")
        except Exception:
            pending = 0
        try:
            dirty = self.conversations.count_memory_dirty()
        except Exception:
            dirty = 0
        if self.search_index is not None:
            try:
                embed_pending = self.search_index.count_embed_pending()
            except Exception:
                embed_pending = None
        return {
            "session_observe_pending": pending,
            "memory_dirty_conversations": dirty,
            "embed_pending": embed_pending,
        }

    def _purpose_stats(self, now: datetime) -> dict[str, Any]:
        since_24 = (now - timedelta(hours=24)).isoformat()
        since_7 = (now - timedelta(days=7)).isoformat()
        out: dict[str, Any] = {}
        for purpose in ALL_PURPOSE_KEYS:
            out[purpose] = self.usage_store.background_purpose_stats(
                purpose, since_24h=since_24, since_7d=since_7
            )
        return out

    def _totals_24h(self, now: datetime, stats: dict[str, Any]) -> dict[str, Any]:
        since_24 = (now - timedelta(hours=24)).isoformat()
        agg = self.usage_store.background_totals_since(since_24)
        return {
            "calls": int(agg.get("calls") or 0),
            "errors": int(agg.get("errors") or 0),
            "prompt_tokens": int(agg.get("prompt_tokens") or 0),
            "completion_tokens": int(agg.get("completion_tokens") or 0),
            "cost": agg.get("cost"),
        }
