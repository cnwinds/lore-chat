"""检索命中强度评估与门控。"""

from __future__ import annotations

from dataclasses import dataclass

from app.index.search_query import CompiledSearchQuery
from app.index.types import Hit

VECTOR_RELATIVE_TOP_MAX = 0.55
VECTOR_RELATIVE_GAP_MIN = 0.03


@dataclass(frozen=True)
class HitMeta:
    lane: str
    fts_tier: str | None = None
    vector_score: float | None = None


def matched_signal_count(chunk: str, terms: tuple[str, ...]) -> int:
    if not terms:
        return 0
    hay = chunk.lower()
    count = 0
    for term in terms:
        if " " in term:
            if term.lower() in hay or term in chunk:
                count += 1
        elif term.lower() in hay or term in chunk:
            count += 1
    return count


def classify_hit_strength(
    hit: Hit,
    meta: HitMeta,
    *,
    compiled: CompiledSearchQuery,
    min_vector_score: float,
) -> str:
    terms = compiled.match_terms or compiled.signal_terms
    need = 1 if len(terms) <= 2 else 2
    if meta.vector_score is not None and meta.vector_score >= min_vector_score:
        return "strong"
    if meta.fts_tier == "strict":
        return "strong"
    if meta.fts_tier == "relaxed":
        if len(compiled.signal_terms) <= 1:
            return "strong"
        if matched_signal_count(hit.chunk, terms) >= need:
            return "strong"
        return "weak"
    if meta.fts_tier == "like":
        if matched_signal_count(hit.chunk, terms) >= need:
            return "strong"
        return "weak"
    return "weak"


def assess_lane_strength(
    doc_ids: list[str],
    meta_map: dict[str, HitMeta],
    hit_map: dict[str, Hit],
    *,
    compiled: CompiledSearchQuery,
    min_vector_score: float,
) -> str:
    """评估某组 lane 合并后的最强命中（strong / weak / none）。"""
    best = "none"
    for doc_id in doc_ids:
        meta = meta_map.get(doc_id)
        hit = hit_map.get(doc_id)
        if not meta or not hit:
            continue
        strength = classify_hit_strength(
            hit, meta, compiled=compiled, min_vector_score=min_vector_score
        )
        if strength == "strong":
            return "strong"
        if strength == "weak":
            best = "weak"
    return best


def gate_page_hits(
    page_hits: list[Hit],
    meta_map: dict[str, HitMeta],
    *,
    compiled: CompiledSearchQuery,
    min_vector_score: float,
) -> tuple[list[Hit], str]:
    """精度优先：仅保留 strong；全无 strong 时返回空并标 weak/none。"""
    if not page_hits:
        return [], "none"

    ranked: list[tuple[Hit, str]] = []
    for hit in page_hits:
        meta = meta_map.get(hit.doc_id)
        if not meta:
            ranked.append((hit, "weak"))
            continue
        ranked.append(
            (
                hit,
                classify_hit_strength(
                    hit,
                    meta,
                    compiled=compiled,
                    min_vector_score=min_vector_score,
                ),
            )
        )

    strong = [h for h, s in ranked if s == "strong"]
    if strong:
        return strong, "strong"
    if any(s == "weak" for _, s in ranked):
        return [], "weak"
    return [], "none"


def should_drop_vector_lane(hits: list[Hit]) -> bool:
    """相对截断：top 向量分偏低且与次席差距过小。"""
    if len(hits) < 2:
        return False
    ordered = sorted(hits, key=lambda h: h.score, reverse=True)
    top, second = ordered[0].score, ordered[1].score
    return top < VECTOR_RELATIVE_TOP_MAX and (top - second) < VECTOR_RELATIVE_GAP_MIN
