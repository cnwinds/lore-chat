from __future__ import annotations

from app.config import Settings
from app.engine.web.search_backends import (
    BraveSearchProvider,
    SearchResult,
    SerperProvider,
    TavilyProvider,
    WebSearchProvider,
)
from app.engine.web.search_router import (
    NoSearchProviderAvailable,
    resolve_search_candidates,
    select_search_provider,
)
from app.models.cooldown import CooldownStore, classify_error

__all__ = [
    "BraveSearchProvider",
    "SearchResult",
    "SerperProvider",
    "TavilyProvider",
    "WebSearch",
    "WebSearchProvider",
]


class WebSearch:
    def __init__(self, settings: Settings, *, cooldown: CooldownStore):
        """cooldown 须与 Container.search_cooldown 同一实例（见 CONTEXT.md）。"""
        self.settings = settings
        self.cooldown = cooldown
        self.provider_name: str | None = None

    @property
    def provider(self) -> WebSearchProvider | None:
        """兼容门控：链上是否至少有一个已配置密钥的提供商。"""
        cands = resolve_search_candidates(self.settings)
        if not cands:
            return None
        return cands[0].provider

    def rebind_settings(self, settings: Settings) -> None:
        self.settings = settings

    async def search(self, query: str, k: int = 5) -> tuple[list[SearchResult], str | None]:
        if not resolve_search_candidates(self.settings):
            return [], "未配置搜索 API，请在设置中添加搜索提供商"

        attempted: set[str] = set()
        last_exc: BaseException | None = None
        while True:
            try:
                sel = select_search_provider(
                    self.settings, self.cooldown, exclude_ids=attempted
                )
            except NoSearchProviderAvailable:
                if last_exc is not None:
                    return [], f"搜索失败：{last_exc}"
                return [], "搜索提供商均不可用（冷却或已禁用），请稍后重试或在设置中调整"

            entry = sel.entry
            try:
                results = await sel.candidate.provider.search(query, k=k)
            except BaseException as e:
                last_exc = e
                self.cooldown.record_failure(
                    entry.id, classify_error(e), error=str(e)
                )
                attempted.add(entry.id)
                continue

            self.cooldown.record_success(entry.id)
            self.provider_name = entry.provider
            return results, None
