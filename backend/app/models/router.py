"""按链选择可用候选（能力过滤 + 冷却）。"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.candidate import ModelCandidate, ModelChain, resolve_chain_candidates
from app.models.cooldown import CooldownStore


@dataclass
class Selection:
    candidate: ModelCandidate
    skipped: list[tuple[str, str]]  # (candidate_id, reason)
    failover: bool  # True if not the first eligible by priority alone


class NoCandidateAvailable(Exception):
    def __init__(self, chain: ModelChain, skipped: list[tuple[str, str]]):
        self.chain = chain
        self.skipped = skipped
        reasons = "; ".join(f"{i}: {r}" for i, r in skipped) or "empty"
        super().__init__(f"no available model on {chain} chain ({reasons})")


def select_candidate(
    settings,
    chain: ModelChain,
    cooldown: CooldownStore,
    *,
    require_image: bool = False,
    exclude_ids: set[str] | frozenset[str] | None = None,
) -> Selection:
    candidates = resolve_chain_candidates(settings, chain)
    skipped: list[tuple[str, str]] = []
    first_priority_id = candidates[0].id if candidates else ""
    excluded = exclude_ids or frozenset()

    eligible: list[ModelCandidate] = []
    for c in candidates:
        if c.id in excluded:
            skipped.append((c.id, "excluded"))
            continue
        if require_image and not c.image:
            skipped.append((c.id, "no_image"))
            continue
        if c.image_wire == "url" and require_image:
            public = (getattr(settings, "public_base_url", None) or "").strip()
            if not public:
                skipped.append((c.id, "public_base_url_required"))
                continue
        if not cooldown.is_available(c.id):
            h = cooldown.get(c.id)
            reason = "disabled" if h.disabled else "cooling"
            skipped.append((c.id, reason))
            continue
        eligible.append(c)

    if not eligible:
        raise NoCandidateAvailable(chain, skipped)

    chosen = eligible[0]
    failover = chosen.id != first_priority_id
    return Selection(candidate=chosen, skipped=skipped, failover=failover)
