"""按搜索提供商链选择可用候选（冷却 + 本轮排除）。"""

from __future__ import annotations

from dataclasses import dataclass

from app.engine.web.search_backends import WebSearchProvider, build_provider
from app.engine.web.search_providers import SearchProviderEntry, parse_search_providers
from app.models.cooldown import CooldownStore

_FAILOVER_SKIP_REASONS = frozenset({"cooling", "disabled", "excluded"})


@dataclass
class ResolvedSearchCandidate:
    entry: SearchProviderEntry
    provider: WebSearchProvider


@dataclass
class SearchSelection:
    candidate: ResolvedSearchCandidate
    skipped: list[tuple[str, str]]
    failover: bool

    @property
    def entry(self) -> SearchProviderEntry:
        return self.candidate.entry


class NoSearchProviderAvailable(Exception):
    def __init__(self, skipped: list[tuple[str, str]]):
        self.skipped = skipped
        reasons = "; ".join(f"{i}: {r}" for i, r in skipped) or "empty"
        super().__init__(f"no available search provider ({reasons})")


def resolve_search_candidates(settings) -> list[ResolvedSearchCandidate]:
    """有 key 的链条目并实例化 Provider。

    - `search_providers` 为 list（含 []）：只读链，不回退 legacy。
    - 为 None：从旧三密钥兼容（.env / 测试 Settings）。
    """
    from app.engine.web.search_providers import legacy_search_entries_from_aliases

    raw = getattr(settings, "search_providers", None)
    if isinstance(raw, list):
        entries = parse_search_providers(raw)
    else:
        data = (
            settings.model_dump()
            if hasattr(settings, "model_dump")
            else dict(settings)
        )
        entries = legacy_search_entries_from_aliases(data)
    return [
        ResolvedSearchCandidate(entry=e, provider=build_provider(e))
        for e in entries
        if e.api_key
    ]


def select_search_provider(
    settings,
    cooldown: CooldownStore,
    *,
    exclude_ids: set[str] | frozenset[str] | None = None,
) -> SearchSelection:
    candidates = resolve_search_candidates(settings)
    skipped: list[tuple[str, str]] = []
    excluded = exclude_ids or frozenset()

    eligible: list[ResolvedSearchCandidate] = []
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
        raise NoSearchProviderAvailable(skipped)

    chosen = eligible[0]
    failover = any(reason in _FAILOVER_SKIP_REASONS for _, reason in skipped)
    return SearchSelection(candidate=chosen, skipped=skipped, failover=failover)
