"""按生图提供商链选择可用候选（冷却 + 本轮排除）。"""

from __future__ import annotations

from dataclasses import dataclass

from app.engine.imagegen.backends import ImageGenBackend, build_backend
from app.engine.imagegen.providers import (
    ImageGenProviderEntry,
    parse_image_providers,
)
from app.models.cooldown import CooldownStore

_FAILOVER_SKIP_REASONS = frozenset({"cooling", "disabled", "excluded"})


@dataclass
class ResolvedImageCandidate:
    entry: ImageGenProviderEntry
    backend: ImageGenBackend


@dataclass
class ImageSelection:
    candidate: ResolvedImageCandidate
    skipped: list[tuple[str, str]]
    failover: bool

    @property
    def entry(self) -> ImageGenProviderEntry:
        return self.candidate.entry


class NoImageProviderAvailable(Exception):
    def __init__(self, skipped: list[tuple[str, str]]):
        self.skipped = skipped
        reasons = "; ".join(f"{i}: {r}" for i, r in skipped) or "empty"
        super().__init__(f"no available image provider ({reasons})")


def resolve_image_candidates(settings) -> list[ResolvedImageCandidate]:
    raw = getattr(settings, "image_providers", None)
    if isinstance(settings, dict):
        raw = settings.get("image_providers")
    entries = parse_image_providers(raw if isinstance(raw, list) else [])
    return [
        ResolvedImageCandidate(entry=e, backend=build_backend(e))
        for e in entries
        if e.api_key
    ]


def select_image_provider(
    settings,
    cooldown: CooldownStore,
    *,
    exclude_ids: set[str] | frozenset[str] | None = None,
    prefer_provider: str | None = None,
) -> ImageSelection:
    candidates = resolve_image_candidates(settings)
    # 弱覆盖：优先钉死的 provider/id，失败后仍可 failover 到链上其余条目（ADR §6）
    if prefer_provider:
        pref = prefer_provider.strip().lower()
        preferred = [
            c
            for c in candidates
            if c.entry.provider == pref or c.entry.id == pref
        ]
        if preferred:
            preferred_ids = {c.entry.id for c in preferred}
            rest = [c for c in candidates if c.entry.id not in preferred_ids]
            candidates = preferred + rest
    skipped: list[tuple[str, str]] = []
    excluded = exclude_ids or frozenset()

    eligible: list[ResolvedImageCandidate] = []
    for c in candidates:
        cid = c.entry.id
        if cid in excluded:
            skipped.append((cid, "excluded"))
            continue
        if not cooldown.is_available(cid):
            h = cooldown.get(cid)
            reason = "disabled" if h.disabled else "cooling"
            skipped.append((cid, reason))
            continue
        eligible.append(c)

    if not eligible:
        raise NoImageProviderAvailable(skipped)

    chosen = eligible[0]
    failover = any(reason in _FAILOVER_SKIP_REASONS for _, reason in skipped)
    return ImageSelection(candidate=chosen, skipped=skipped, failover=failover)
