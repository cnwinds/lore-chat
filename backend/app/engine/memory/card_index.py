"""角色知识卡分区索引：同步已确认卡、按轮/召回检索。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.config import Settings
from app.index.partitioned import (
    IndexItem,
    PartitionTuning,
    SearchIndex,
    SyncStats,
    default_gate,
)
from app.engine.memory.owner_index import OWNER_PARTITION
from app.logging_config import get_logger

if TYPE_CHECKING:
    from app.engine.memory.cards import KnowledgeCards

_log = get_logger("memory.card_index")

CARD_FAMILY = "cards"
TURN_CARDS_LIMIT = 5


def card_partition(scope: str) -> str:
    return f"{CARD_FAMILY}:{scope}"


@dataclass
class CardRetrievalTuning:
    min_vector_score: float = 0.55
    vector_timeout_s: float = 0.8
    rare_df_ratio: float = 0.25

    @classmethod
    def from_settings(cls, settings: Settings) -> CardRetrievalTuning:
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


class CardIndex:
    def __init__(
        self,
        index: SearchIndex,
        cards: KnowledgeCards,
        tuning: CardRetrievalTuning | None = None,
    ):
        self.index = index
        self.cards = cards
        self.tuning = tuning or CardRetrievalTuning()

    def sync_scope_locked(self, scope: str) -> SyncStats:
        partition = card_partition(scope)
        items = [
            IndexItem(
                item_id=fact["id"],
                text=fact["statement"],
                meta={
                    "kind": fact.get("category") or "",
                    "origin": fact.get("origin") or "",
                },
            )
            for fact in self.cards.store(scope).list_confirmed()
        ]
        return self.index.sync_partition(partition, items)

    def drop_scope(self, scope: str) -> int:
        return self.index.drop_partition(card_partition(scope))

    def sync_all(self) -> dict:
        scopes = self.cards.list_scopes()
        scope_set = set(scopes)
        totals = {"added": 0, "updated": 0, "removed": 0, "unchanged": 0}
        for scope in scopes:
            try:
                with self.cards.scope_lock(scope):
                    stats = self.sync_scope_locked(scope)
                totals["added"] += stats.added
                totals["updated"] += stats.updated
                totals["removed"] += stats.removed
                totals["unchanged"] += stats.unchanged
            except Exception as exc:  # noqa: BLE001
                _log.warning("card index sync failed scope=%s err=%s", scope, exc)
        dropped = 0
        for partition in self.index.partitions(CARD_FAMILY):
            # cards:<scope>，scope 本身可含冒号
            if partition == OWNER_PARTITION:
                continue
            scope_key = partition[len(CARD_FAMILY) + 1 :]
            if scope_key not in scope_set:
                try:
                    dropped += self.index.drop_partition(partition)
                except Exception as exc:  # noqa: BLE001
                    _log.warning(
                        "card index drop orphan partition=%s err=%s",
                        partition,
                        exc,
                    )
        return {
            "scopes": len(scopes),
            "dropped_partitions": dropped,
            **totals,
        }

    def rebuild(self) -> dict:
        for partition in list(self.index.partitions(CARD_FAMILY)):
            try:
                self.index.drop_partition(partition)
            except Exception as exc:  # noqa: BLE001
                _log.warning(
                    "card index rebuild drop failed partition=%s err=%s",
                    partition,
                    exc,
                )
        stats = self.sync_all()
        cards_indexed = sum(
            len(self.cards.store(scope).list_confirmed())
            for scope in self.cards.list_scopes()
        )
        return {**stats, "cards_indexed": cards_indexed}

    def search(
        self,
        scope: str,
        query: str,
        *,
        limit: int,
        exclude_ids: set[str] | frozenset[str] = frozenset(),
        mode: str = "turn",
    ) -> list[dict]:
        if mode not in ("turn", "recall"):
            raise ValueError(f"invalid card search mode: {mode!r}")
        confirmed = {
            f["id"]: f for f in self.cards.store(scope).list_confirmed()
        }
        eligible = set(confirmed.keys()) - set(exclude_ids)
        q = (query or "").strip()
        if not eligible or not q:
            return []

        candidate_k = min(200, max(20, limit + len(exclude_ids)))
        pt = self.tuning.partition_tuning(candidate_k=candidate_k)
        try:
            res = self.index.search(
                q,
                partitions=[card_partition(scope)],
                limit=candidate_k,
                tunings={CARD_FAMILY: pt},
                vector_timeout_s=self.tuning.vector_timeout_s,
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning(
                "card index search failed scope=%s err=%s", scope, exc
            )
            return []

        out: list[dict] = []
        for hit in res.hits:
            fact = confirmed.get(hit.item_id)
            if fact is None or hit.item_id in exclude_ids:
                continue
            if mode == "turn" and not default_gate(hit, pt):
                continue
            if mode == "recall" and not (
                hit.matched_terms
                or (hit.vector_score or 0) >= pt.min_vector_score
            ):
                continue
            out.append(fact)
            if len(out) >= limit:
                break
        return out
