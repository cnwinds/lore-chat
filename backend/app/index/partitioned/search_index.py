from __future__ import annotations

import json
import math
import re
import threading
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.index.partitioned.embedder import EmbedBatch, Embedder, QueryEmbedCache
from app.index.partitioned.lexical import (
    FAMILIES,
    PartitionedLexical,
    content_hash,
    partition_family,
    validate_meta,
)
from app.index.partitioned.tokenize import index_terms, query_terms
from app.index.partitioned.vectors import PartitionedVectors
from app.index.search_query import compile_search_query
from app.logging_config import get_logger

_log = get_logger("partitioned_index")

_META_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_VALID_OPS = frozenset({"eq", "ne", "gte", "lt"})


@dataclass(frozen=True)
class MetaFilter:
    key: str
    op: str
    value: str | int | float | bool

    def __post_init__(self) -> None:
        if not _META_KEY_RE.match(self.key):
            raise ValueError(f"invalid meta filter key: {self.key!r}")
        if self.op not in _VALID_OPS:
            raise ValueError(f"invalid meta filter op: {self.op!r}")


@dataclass(frozen=True)
class IndexItem:
    item_id: str
    text: str
    meta: Mapping[str, str | int | float | bool] = field(default_factory=dict)


@dataclass(frozen=True)
class PartitionTuning:
    fts_k: int = 20
    vec_k: int = 20
    fts_weight: float = 1.0
    vec_weight: float = 1.0
    min_vector_score: float = 0.5
    rare_df_ratio: float = 0.25


@dataclass(frozen=True)
class SyncStats:
    added: int = 0
    updated: int = 0
    removed: int = 0
    unchanged: int = 0


@dataclass(frozen=True)
class SearchHit:
    partition: str
    item_id: str
    text: str
    meta: dict
    score: float
    bm25: float | None
    matched_terms: tuple[str, ...]
    rare_terms: tuple[str, ...]
    vector_score: float | None


@dataclass(frozen=True)
class SearchResult:
    hits: list[SearchHit]
    vector_status: str
    query_terms: tuple[str, ...]
    elapsed_ms: int
    lanes: dict[str, list[SearchHit]] = field(default_factory=dict)
    fts_tiers: dict[str, str] = field(default_factory=dict)


def default_gate(hit: SearchHit, tuning: PartitionTuning) -> bool:
    return (
        hit.vector_score is not None
        and hit.vector_score >= tuning.min_vector_score
    ) or bool(hit.rare_terms)


def _meta_value_passes(
    meta: dict,
    flt: MetaFilter,
) -> bool:
    raw = meta.get(flt.key)
    if flt.op == "eq":
        return raw is not None and raw == flt.value
    if flt.op == "ne":
        return raw is None or raw != flt.value
    if raw is None:
        return False
    if flt.op == "gte":
        try:
            return raw >= flt.value
        except TypeError:
            return False
    if flt.op == "lt":
        try:
            return raw < flt.value
        except TypeError:
            return False
    return False


def _passes_meta_filters(meta: dict, filters: Sequence[MetaFilter]) -> bool:
    return all(_meta_value_passes(meta, flt) for flt in filters)


def _like_pattern(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _keyword_phrase(term: str) -> str | None:
    tokens = index_terms(term)
    if not tokens:
        return None
    inner = " ".join(t.replace('"', '""') for t in tokens)
    return f'"{inner}"'


class SearchIndex:
    QUERY_MAX_CHARS = 2000
    MAX_QUERY_TERMS = 64
    _PROBE_TEXT = "模型探测"

    def __init__(
        self,
        db_path: str | Path,
        vec_path: str | Path,
        embedder: Embedder | None,
        *,
        rrf_k: int = 60,
    ):
        self._lexical = PartitionedLexical(db_path)
        self._vectors = PartitionedVectors(vec_path)
        self._embedder = embedder
        self.rrf_k = rrf_k
        self._write_lock = threading.RLock()
        self._query_cache = QueryEmbedCache()
        self._executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="pidx-embed"
        )
        self._closed = False
        self._warn_last: dict[str, float] = {}
        self._probe_needed = False
        self._probe_next_at = 0.0
        self._held_families: dict[str, int] = defaultdict(int)
        self._held_lock = threading.Lock()

    @property
    def embedder(self) -> Embedder | None:
        return self._embedder

    @embedder.setter
    def embedder(self, value: Embedder | None) -> None:
        self._embedder = value

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._executor.shutdown(wait=False, cancel_futures=True)
        self._vectors.close()

    def get_meta(self, key: str) -> str | None:
        return self._lexical.get_meta(key)

    def set_meta(self, key: str, value: str) -> None:
        self._lexical.set_meta(key, value)

    def on_embedder_changed(self) -> None:
        with self._write_lock:
            self._lexical.on_embedder_changed()
            self._probe_needed = True
            self._probe_next_at = 0.0
        self._query_cache.clear()

    def _active_embed_model(self) -> str | None:
        return self._lexical.get_meta("active_embed_model")

    def _set_active_embed_model(self, model: str) -> None:
        prev = self._active_embed_model()
        if prev != model:
            _log.info("嵌入模型变更，按需重嵌: %s -> %s", prev, model)
        self._lexical.set_meta("active_embed_model", model)

    def _held_exclude(self) -> frozenset[str]:
        with self._held_lock:
            return frozenset(
                f for f, n in self._held_families.items() if n > 0
            )

    @contextmanager
    def embedding_held(self, family: str):
        if family not in FAMILIES:
            raise ValueError(f"unknown family: {family!r}")
        with self._held_lock:
            self._held_families[family] += 1
        try:
            yield
        finally:
            with self._held_lock:
                self._held_families[family] -= 1
                if self._held_families[family] <= 0:
                    del self._held_families[family]

    def probe_model(self) -> str | None:
        if self._closed or self._embedder is None:
            return None
        try:
            batch = self._embedder.embed([self._PROBE_TEXT])
        except Exception:
            return None
        if batch.model == "unknown":
            return None
        return batch.model

    def adopt_vectors(
        self,
        partition: str,
        rows: Iterable[tuple[str, str, Sequence[float]]],
        *,
        model: str,
    ) -> int:
        active = self._active_embed_model()
        if active is not None and active != model:
            return 0
        batch = list(rows)
        if not batch:
            return 0
        if len(batch) > 256:
            raise ValueError("adopt_vectors batch exceeds 256 rows")
        if active is None:
            self._set_active_embed_model(model)
        family = partition_family(partition)
        item_ids = [r[0] for r in batch]
        with self._write_lock:
            existing = self._lexical.rows_for_adopt(partition, item_ids)
        adopted = 0
        vec_rows: list[
            tuple[str, str, str, list[float], dict[str, str | int | float | bool]]
        ] = []
        ok_keys: list[tuple[str, str, str]] = []
        for item_id, text, embedding in batch:
            row = existing.get(item_id)
            if row is None:
                continue
            if row["text"] != text:
                continue
            if row["vec_state"] == "ok" and row["vec_model"] == model:
                continue
            meta = json.loads(row["meta_json"] or "{}")
            h = row["content_hash"]
            vec_rows.append(
                (partition, item_id, text, list(embedding), meta)
            )
            ok_keys.append((partition, item_id, h))
        if not vec_rows:
            return 0
        with self._write_lock:
            try:
                self._vectors.upsert(family, model, vec_rows)
            except Exception:
                _log.warning(
                    "adopt_vectors 写入失败 partition=%s", partition, exc_info=True
                )
                return 0
            for partition, item_id, h in ok_keys:
                if self._lexical.mark_embed_ok(
                    partition, item_id, content_hash=h, model=model
                ):
                    adopted += 1
        return adopted

    def _warn_throttled(self, key: str, msg: str, *args) -> None:
        now = time.time()
        last = self._warn_last.get(key, 0.0)
        if now - last >= 60.0:
            self._warn_last[key] = now
            _log.warning(msg, *args)

    def _normalize_items(
        self, items: Iterable[IndexItem]
    ) -> dict[str, IndexItem]:
        out: dict[str, IndexItem] = {}
        for item in items:
            text = item.text.strip()
            if not text:
                continue
            meta = validate_meta(item.meta)
            out[item.item_id] = IndexItem(
                item_id=item.item_id, text=text, meta=meta
            )
        return out

    def _apply_vec_deletes(
        self, vec_deletes: list[tuple[str, str, str | None]]
    ) -> None:
        by_model: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for partition, item_id, model in vec_deletes:
            if model:
                family = partition_family(partition)
                by_model[f"{family}\x1f{model}"].append((partition, item_id))
        for key, keys in by_model.items():
            family, model = key.split("\x1f", 1)
            try:
                self._vectors.delete(family, model, keys)
            except Exception:
                _log.warning(
                    "向量删除失败 family=%s model=%s", family, model, exc_info=True
                )

    def _stats_from_counts(self, counts: tuple[int, int, int, int]) -> SyncStats:
        return SyncStats(
            added=counts[0],
            updated=counts[1],
            removed=counts[2],
            unchanged=counts[3],
        )

    def sync_partition(
        self, partition: str, items: Iterable[IndexItem]
    ) -> SyncStats:
        return self._write_partition(partition, items, delete_absent=True)

    def upsert(
        self, partition: str, items: Iterable[IndexItem]
    ) -> SyncStats:
        return self._write_partition(partition, items, delete_absent=False)

    def sync_group(
        self, partition: str, group: str, items: Sequence[IndexItem]
    ) -> SyncStats:
        if not group:
            raise ValueError("group must not be empty")
        if not items:
            removed = self.drop_group(partition, group)
            return SyncStats(removed=removed)
        return self._write_group(partition, group, items, delete_absent=True)

    def drop_group(self, partition: str, group: str) -> int:
        if not group:
            raise ValueError("group must not be empty")
        family = partition_family(partition)
        with self._write_lock:
            removed, vec_deletes = self._lexical.drop_group_tx(
                partition, family, group
            )
        self._apply_vec_deletes(vec_deletes)
        return removed

    def drop_groups(self, partition: str, *, prefix: str) -> int:
        if not prefix:
            raise ValueError("prefix must not be empty")
        family = partition_family(partition)
        with self._write_lock:
            removed, vec_deletes = self._lexical.drop_groups_tx(
                partition, family, prefix
            )
        self._apply_vec_deletes(vec_deletes)
        return removed

    def groups(self, partition: str) -> list[str]:
        partition_family(partition)
        return self._lexical.groups(partition)

    def group_items(self, partition: str, group: str) -> list[IndexItem]:
        rows = self._lexical.group_items(partition, group)
        out: list[IndexItem] = []
        for r in rows:
            meta = json.loads(r["meta_json"] or "{}")
            out.append(
                IndexItem(item_id=r["item_id"], text=r["text"], meta=meta)
            )
        return out

    def _write_group(
        self,
        partition: str,
        group: str,
        items: Iterable[IndexItem],
        *,
        delete_absent: bool,
    ) -> SyncStats:
        family = partition_family(partition)
        normalized = self._normalize_items(items)
        desired = {
            iid: (it.text, dict(it.meta), content_hash(it.text, it.meta))
            for iid, it in normalized.items()
        }
        with self._write_lock:
            counts, vec_deletes = self._lexical.sync_group_tx(
                partition, family, group, desired, delete_absent=delete_absent
            )
        self._apply_vec_deletes(vec_deletes)
        return self._stats_from_counts(counts)

    def _write_partition(
        self,
        partition: str,
        items: Iterable[IndexItem],
        *,
        delete_absent: bool,
    ) -> SyncStats:
        family = partition_family(partition)
        normalized = self._normalize_items(items)
        desired = {
            iid: (it.text, dict(it.meta), content_hash(it.text, it.meta))
            for iid, it in normalized.items()
        }
        with self._write_lock:
            counts, vec_deletes = self._lexical.sync_partition_tx(
                partition, family, desired, delete_absent=delete_absent
            )
        self._apply_vec_deletes(vec_deletes)
        return self._stats_from_counts(counts)

    def delete(self, partition: str, item_ids: Iterable[str]) -> int:
        family = partition_family(partition)
        ids = list(item_ids)
        with self._write_lock:
            removed, vec_deletes = self._lexical.delete_items_tx(
                partition, family, ids
            )
        self._apply_vec_deletes(vec_deletes)
        return removed

    def drop_partition(self, partition: str) -> int:
        family = partition_family(partition)
        with self._write_lock:
            removed, vec_deletes = self._lexical.drop_partition_tx(
                partition, family
            )
        self._apply_vec_deletes(vec_deletes)
        self._vectors.delete_partition(family, partition)
        return removed

    def partitions(self, family: str) -> list[str]:
        if family not in FAMILIES:
            raise ValueError(f"unknown family: {family!r}")
        return self._lexical.partitions(family)

    def _run_probe(self) -> int:
        active = self._active_embed_model()
        if not active or not self._lexical.has_ok_items():
            return 0
        try:
            batch = self._embedder.embed([self._PROBE_TEXT])  # type: ignore[union-attr]
        except Exception as exc:
            with self._write_lock:
                self._probe_next_at = time.time() + 60
            self._warn_throttled(
                type(exc).__name__,
                "嵌入模型探测失败: %s",
                exc,
            )
            return 0
        with self._write_lock:
            self._probe_needed = False
            if batch.model != active:
                self._set_active_embed_model(batch.model)
        return 0

    def embed_pending(self, limit: int = 32) -> int:
        if self._closed or self._embedder is None:
            return 0
        active = self._active_embed_model()
        exclude = self._held_exclude()
        with self._write_lock:
            rows = self._lexical.select_embed_pending(
                limit, active, exclude_families=exclude
            )
            probe_needed = self._probe_needed
            probe_next_at = self._probe_next_at
        if not rows:
            if (
                probe_needed
                and time.time() >= probe_next_at
                and active
                and self._lexical.has_ok_items()
            ):
                return self._run_probe()
            return 0
        snapshots = [
            (
                r["partition"],
                r["item_id"],
                r["content_hash"],
                r["family"],
                r["text"],
                r["vec_model"],
                r["meta_json"],
            )
            for r in rows
        ]
        texts = [s[4] for s in snapshots]
        try:
            batch = self._embedder.embed(texts)
        except Exception as exc:
            keys = [(s[0], s[1]) for s in snapshots]
            with self._write_lock:
                self._lexical.mark_embed_failed(keys, 1)
            self._warn_throttled(
                type(exc).__name__,
                "embed_pending 失败: %s",
                exc,
            )
            return 0

        model = batch.model
        written = 0
        old_models_to_check: set[tuple[str, str]] = set()

        with self._write_lock:
            if not active or active != model:
                self._set_active_embed_model(model)

            by_family: dict[
                str,
                list[
                    tuple[
                        str,
                        str,
                        str,
                        list[float],
                        str,
                        str | None,
                        dict,
                    ]
                ],
            ] = defaultdict(list)
            for i, snap in enumerate(snapshots):
                partition, item_id, h, family, text, old_model, meta_json = snap
                row = self._lexical.get_item(partition, item_id)
                if row is None or row["content_hash"] != h:
                    continue
                meta = json.loads(meta_json or "{}")
                by_family[family].append(
                    (partition, item_id, text, batch.vectors[i], h, old_model, meta)
                )

            for family, items in by_family.items():
                upsert_rows = [
                    (p, iid, text, vec, meta)
                    for p, iid, text, vec, _h, _o, meta in items
                ]
                try:
                    self._vectors.upsert(family, model, upsert_rows)
                except Exception:
                    fail_keys = [(p, iid) for p, iid, *_ in items]
                    self._lexical.mark_embed_failed(fail_keys, 1)
                    _log.warning(
                        "向量写入失败 family=%s model=%s",
                        family,
                        model,
                        exc_info=True,
                    )
                    continue
                for p, iid, _text, _vec, h, old_model, _meta in items:
                    if not self._lexical.mark_embed_ok(
                        p, iid, content_hash=h, model=model
                    ):
                        continue
                    written += 1
                    if old_model and old_model != model:
                        old_models_to_check.add((family, old_model))
                        self._vectors.delete(family, old_model, [(p, iid)])

            for family, old_model in old_models_to_check:
                if self._lexical.count_by_vec_model(family, old_model) == 0:
                    self._vectors.drop_collection(family, old_model)

        return written

    @staticmethod
    def _fts_match_expr(terms: list[str]) -> str:
        parts = []
        for t in terms:
            parts.append('"' + t.replace('"', '""') + '"')
        return " OR ".join(parts)

    def _select_query_terms(
        self, family: str, terms: list[str]
    ) -> tuple[tuple[str, ...], dict[str, int]]:
        if not terms:
            return (), {}
        doc_map = self._lexical.vocab_docs(family, terms)
        usable = [t for t in terms if t in doc_map]
        if len(usable) > self.MAX_QUERY_TERMS:
            usable.sort(key=lambda t: (doc_map[t], terms.index(t)))
            usable = usable[: self.MAX_QUERY_TERMS]
        return tuple(usable), doc_map

    def _compute_term_sets(
        self,
        text: str,
        query_term_list: list[str],
        doc_map: dict[str, int],
        threshold: int,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        indexed = set(index_terms(text))
        matched = tuple(t for t in query_term_list if t in indexed)
        rare = tuple(t for t in matched if doc_map.get(t, 0) <= threshold)
        return matched, rare

    def _fts_keywords_for_family(
        self,
        family: str,
        parts: list[str],
        compiled,
        tuning: PartitionTuning,
        filters: Sequence[MetaFilter],
    ) -> tuple[list[tuple[str, str, float]], str]:
        phrases = []
        for term in compiled.signal_terms:
            ph = _keyword_phrase(term)
            if ph:
                phrases.append(ph)
        if not phrases:
            return [], "none"

        n_ph = len(phrases)
        if n_ph == 1:
            strict_expr = phrases[0]
        elif n_ph <= 4:
            strict_expr = " AND ".join(phrases)
        else:
            strict_expr = None

        if strict_expr:
            hits = self._lexical.fts_search(
                family,
                strict_expr,
                parts,
                tuning.fts_k,
                filters,
            )
            if hits:
                return hits, "strict"

        relaxed_expr = " OR ".join(phrases)
        hits = self._lexical.fts_search(
            family,
            relaxed_expr,
            parts,
            tuning.fts_k,
            filters,
        )
        if hits:
            return hits, "relaxed"

        like_ordered = sorted(
            compiled.like_terms, key=lambda t: len(list(t)), reverse=True
        )
        for term in like_ordered:
            pattern = _like_pattern(term)
            hits = self._lexical.like_search(
                family, pattern, parts, tuning.fts_k, filters
            )
            if hits:
                return hits, "like"

        return [], "none"

    def search(
        self,
        query: str,
        *,
        partitions: Sequence[str],
        limit: int = 10,
        tunings: Mapping[str, PartitionTuning] | None = None,
        vector_timeout_s: float | None = None,
        lanes: tuple[str, ...] = ("fts", "vec"),
        fts_mode: str = "natural",
        vector_text: str | None = None,
        filters: Sequence[MetaFilter] = (),
    ) -> SearchResult:
        t0 = time.monotonic()
        if not partitions:
            raise ValueError("partitions must not be empty")
        if fts_mode not in ("natural", "keywords"):
            raise ValueError(f"unknown fts_mode: {fts_mode!r}")
        uniq_partitions: list[str] = []
        seen_p: set[str] = set()
        by_family: dict[str, list[str]] = defaultdict(list)
        for p in partitions:
            if p in seen_p:
                continue
            partition_family(p)
            seen_p.add(p)
            uniq_partitions.append(p)
            by_family[partition_family(p)].append(p)

        q = query.strip()[: self.QUERY_MAX_CHARS]
        if not q:
            return SearchResult([], "skipped", (), 0)

        embed_source = (
            vector_text.strip()[: self.QUERY_MAX_CHARS]
            if vector_text is not None
            else q
        )

        tunings = tunings or {}
        embed_future: Future[EmbedBatch] | None = None
        embed_batch: EmbedBatch | None = None
        vector_status = "skipped"

        active_model = self._active_embed_model()

        if "vec" not in lanes:
            vector_status = "skipped"
        elif self._closed or self._embedder is None:
            vector_status = "unavailable"
        else:
            cached = None
            if active_model:
                cached = self._query_cache.get(embed_source, active_model)
            if cached is not None:
                embed_batch = cached
            else:

                def _do_embed() -> EmbedBatch:
                    return self._embedder.embed([embed_source])  # type: ignore[union-attr]

                embed_future = self._executor.submit(_do_embed)

                def _cache_done(fut: Future) -> None:
                    try:
                        batch = fut.result()
                        self._query_cache.put(embed_source, batch.model, batch)
                    except Exception:
                        pass

                embed_future.add_done_callback(_cache_done)

        compiled_kw = None
        if fts_mode == "keywords":
            compiled_kw = compile_search_query(q)

        all_terms = query_terms(q)
        family_term_docs: dict[str, tuple[tuple[str, ...], dict[str, int]]] = {}
        fts_hits_by_family: dict[str, list[tuple[str, str, float]]] = {}
        fts_tiers: dict[str, str] = {}
        family_thresholds: dict[str, int] = {}

        for family, parts in by_family.items():
            sel_terms, doc_map = self._select_query_terms(family, all_terms)
            family_term_docs[family] = (sel_terms, doc_map)
            n = self._lexical.count_family(family)
            tuning = tunings.get(family, PartitionTuning())
            family_thresholds[family] = max(
                1, math.floor(n * tuning.rare_df_ratio)
            )
            if "fts" not in lanes:
                fts_hits_by_family[family] = []
                fts_tiers[family] = "none"
            elif fts_mode == "keywords" and compiled_kw is not None:
                hits, tier = self._fts_keywords_for_family(
                    family, parts, compiled_kw, tuning, filters
                )
                fts_hits_by_family[family] = hits
                fts_tiers[family] = tier
            elif sel_terms:
                expr = self._fts_match_expr(list(sel_terms))
                fts_hits_by_family[family] = self._lexical.fts_search(
                    family,
                    expr,
                    parts,
                    tuning.fts_k,
                    filters,
                )
                fts_tiers[family] = "natural"
            else:
                fts_hits_by_family[family] = []
                fts_tiers[family] = "natural"

        eq_ne_filters = [f for f in filters if f.op in ("eq", "ne")]
        range_filters = [f for f in filters if f.op in ("gte", "lt")]

        vec_hits_by_family: dict[str, list[tuple[str, str, float]]] = {}
        if "vec" in lanes and not self._closed and self._embedder is not None:
            batch = embed_batch
            if batch is None and embed_future is not None:
                elapsed = time.monotonic() - t0
                remaining = (
                    None
                    if vector_timeout_s is None
                    else vector_timeout_s - elapsed
                )
                if remaining is not None and remaining <= 0:
                    vector_status = "timeout"
                else:
                    try:
                        if remaining is None:
                            batch = embed_future.result()
                        else:
                            batch = embed_future.result(timeout=remaining)
                        self._query_cache.put(
                            embed_source, batch.model, batch
                        )
                    except TimeoutError:
                        vector_status = "timeout"
                    except Exception as exc:
                        vector_status = "error"
                        _log.debug("查询嵌入失败: %s", exc)

            if vector_status not in ("timeout", "error") and batch is not None:
                active = self._active_embed_model()
                if not active or batch.model != active:
                    vector_status = "model_mismatch"
                    if active and batch.model != active:
                        with self._write_lock:
                            self._probe_needed = True
                else:
                    emb = batch.vectors[0]
                    vector_status = "ok"
                    for family, parts in by_family.items():
                        tuning = tunings.get(family, PartitionTuning())
                        n_res = tuning.vec_k
                        if range_filters:
                            n_res = tuning.vec_k * 8
                        try:
                            raw_hits = self._vectors.query(
                                family,
                                active,
                                emb,
                                partitions=parts,
                                k=tuning.vec_k,
                                eq_ne_filters=eq_ne_filters,
                                n_results=n_res,
                            )
                        except Exception as exc:
                            vector_status = "error"
                            vec_hits_by_family = {}
                            _log.debug("向量查询失败: %s", exc)
                            break
                        if filters:
                            keys = [(p, i) for p, i, _ in raw_hits]
                            rows = self._lexical.fetch_items(keys)
                            filtered: list[tuple[str, str, float]] = []
                            for partition, item_id, score in raw_hits:
                                row = rows.get((partition, item_id))
                                if row is None:
                                    continue
                                meta = json.loads(row["meta_json"] or "{}")
                                if _passes_meta_filters(meta, filters):
                                    filtered.append(
                                        (partition, item_id, score)
                                    )
                            vec_hits_by_family[family] = filtered[: tuning.vec_k]
                        else:
                            vec_hits_by_family[family] = raw_hits[: tuning.vec_k]

        merged: dict[tuple[str, str], dict] = {}
        query_term_list = list(all_terms)

        for family in by_family:
            tuning = tunings.get(family, PartitionTuning())
            fts_ranked = fts_hits_by_family.get(family, [])
            for rank, (partition, item_id, bm25) in enumerate(
                fts_ranked, start=1
            ):
                key = (partition, item_id)
                entry = merged.setdefault(
                    key,
                    {
                        "score": 0.0,
                        "bm25": None,
                        "vector_score": None,
                        "matched_terms": (),
                        "rare_terms": (),
                    },
                )
                entry["score"] += tuning.fts_weight / (self.rrf_k + rank)
                entry["bm25"] = bm25

            vec_ranked = vec_hits_by_family.get(family, [])
            for rank, (partition, item_id, vscore) in enumerate(
                vec_ranked, start=1
            ):
                key = (partition, item_id)
                entry = merged.setdefault(
                    key,
                    {
                        "score": 0.0,
                        "bm25": None,
                        "vector_score": None,
                        "matched_terms": (),
                        "rare_terms": (),
                    },
                )
                entry["score"] += tuning.vec_weight / (self.rrf_k + rank)
                entry["vector_score"] = vscore

        if merged:
            rows = self._lexical.fetch_items(merged.keys())
            for key, entry in list(merged.items()):
                row = rows.get(key)
                if row is None:
                    del merged[key]
                    continue
                meta = json.loads(row["meta_json"] or "{}")
                if filters and not _passes_meta_filters(meta, filters):
                    del merged[key]
                    continue
                text = row["text"]
                matched, rare = self._compute_term_sets(
                    text,
                    query_term_list,
                    family_term_docs[partition_family(key[0])][1],
                    family_thresholds[partition_family(key[0])],
                )
                entry["text"] = text
                entry["meta"] = meta
                if entry["bm25"] is not None:
                    entry["matched_terms"] = matched
                    entry["rare_terms"] = rare
                elif entry["matched_terms"] == ():
                    entry["matched_terms"] = matched
                    entry["rare_terms"] = rare

        hit_by_key: dict[tuple[str, str], SearchHit] = {}
        for (partition, item_id), entry in merged.items():
            hit_by_key[(partition, item_id)] = SearchHit(
                partition=partition,
                item_id=item_id,
                text=entry["text"],
                meta=entry["meta"],
                score=entry["score"],
                bm25=entry["bm25"],
                matched_terms=entry["matched_terms"],
                rare_terms=entry["rare_terms"],
                vector_score=entry["vector_score"],
            )

        lane_map: dict[str, list[SearchHit]] = {}
        for family in by_family:
            fts_key = f"{family}:fts"
            vec_key = f"{family}:vec"
            fts_list: list[SearchHit] = []
            for partition, item_id, _bm in fts_hits_by_family.get(family, []):
                key = (partition, item_id)
                if key in hit_by_key:
                    fts_list.append(hit_by_key[key])
            vec_list: list[SearchHit] = []
            for partition, item_id, _vs in vec_hits_by_family.get(family, []):
                key = (partition, item_id)
                if key in hit_by_key:
                    vec_list.append(hit_by_key[key])
            if fts_list:
                lane_map[fts_key] = fts_list
            if vec_list:
                lane_map[vec_key] = vec_list

        hits = sorted(
            hit_by_key.values(),
            key=lambda h: (
                -h.score,
                -(h.vector_score or -1.0),
                -(h.bm25 or -1.0),
            ),
        )[:limit]

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        return SearchResult(
            hits=hits,
            vector_status=vector_status,
            query_terms=tuple(all_terms),
            elapsed_ms=elapsed_ms,
            lanes=lane_map,
            fts_tiers=fts_tiers,
        )
