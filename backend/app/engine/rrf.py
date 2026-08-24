from __future__ import annotations


def reciprocal_rank_fusion(
    ranked_id_lists: list[list[str]],
    *,
    k: int = 60,
    weights: list[float] | None = None,
) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for i, ranked in enumerate(ranked_id_lists):
        w = weights[i] if weights is not None and i < len(weights) else 1.0
        for rank, doc_id in enumerate(ranked, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + w * (1.0 / (k + rank))
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
