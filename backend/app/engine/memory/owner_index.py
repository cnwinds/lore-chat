"""主人记忆分区索引 `cards:owner`：同步已确认事实、检索后回源。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.config import Settings
from app.index.partitioned import (
    IndexItem,
    MetaFilter,
    PartitionTuning,
    SearchIndex,
    SyncStats,
)
from app.logging_config import get_logger

if TYPE_CHECKING:
    from app.engine.memory.store import MemoryStore

_log = get_logger("memory.owner_index")

OWNER_PARTITION = "cards:owner"
CARD_FAMILY = "cards"


@dataclass
class OwnerRetrievalTuning:
    min_vector_score: float = 0.55
    vector_timeout_s: float = 0.8
    rare_df_ratio: float = 0.25

    @classmethod
    def from_settings(cls, settings: Settings) -> OwnerRetrievalTuning:
        return cls(
            min_vector_score=settings.card_retrieval_min_vector_score,
            vector_timeout_s=max(0.0, int(settings.retrieval_vector_timeout_ms))
            / 1000.0,
            rare_df_ratio=0.25,
        )

    def partition_tuning(self, *, candidate_k: int) -> PartitionTuning:
        return PartitionTuning(
            fts_k=candidate_k,
            vec_k=candidate_k,
            min_vector_score=self.min_vector_score,
            rare_df_ratio=self.rare_df_ratio,
        )


class OwnerMemoryIndex:
    def __init__(
        self,
        index: SearchIndex,
        store: MemoryStore,
        tuning: OwnerRetrievalTuning | None = None,
    ):
        self.index = index
        self.store = store
        self.tuning = tuning or OwnerRetrievalTuning()

    def sync(self) -> SyncStats:
        items = [
            IndexItem(
                item_id=fact["id"],
                text=fact["statement"],
                meta={
                    "kind": fact.get("category") or "",
                    "origin": fact.get("origin") or "",
                },
            )
            for fact in self.store.list_confirmed()
        ]
        return self.index.sync_partition(OWNER_PARTITION, items)

    def rebuild(self) -> dict:
        try:
            self.index.drop_partition(OWNER_PARTITION)
        except Exception as exc:  # noqa: BLE001
            _log.warning("owner index rebuild drop failed err=%s", exc)
        stats = self.sync()
        return {
            **stats.__dict__,
            "facts_indexed": len(self.store.list_confirmed()),
        }

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        kind: str | None = None,
    ) -> list[dict]:
        q = (query or "").strip()
        if not q:
            return []

        confirmed = {f["id"]: f for f in self.store.list_confirmed()}
        if not confirmed:
            return []

        filters: list[MetaFilter] = []
        if kind:
            filters.append(MetaFilter("kind", "eq", kind))

        candidate_k = min(200, max(20, limit * 4))
        pt = self.tuning.partition_tuning(candidate_k=candidate_k)
        try:
            res = self.index.search(
                q,
                partitions=[OWNER_PARTITION],
                limit=candidate_k,
                tunings={CARD_FAMILY: pt},
                vector_timeout_s=self.tuning.vector_timeout_s,
                fts_mode="natural",
                filters=filters,
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning("owner index search failed err=%s", exc)
            return []

        out: list[dict] = []
        for hit in res.hits:
            fact = confirmed.get(hit.item_id)
            if fact is None:
                continue
            if not (
                hit.matched_terms
                or (hit.vector_score or 0) >= pt.min_vector_score
            ):
                continue
            out.append(fact)
            if len(out) >= limit:
                break
        return out
