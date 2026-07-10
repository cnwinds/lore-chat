from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import Settings


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


class WebSearchProvider(Protocol):
    async def search(self, query: str, k: int = 5) -> list[SearchResult]: ...


class TavilyProvider:
    def __init__(self, api_key: str):
        self._api_key = api_key

    async def search(self, query: str, k: int = 5) -> list[SearchResult]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": self._api_key, "query": query, "max_results": k},
            )
            resp.raise_for_status()
            data = resp.json()
        return [
            SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content", ""),
            )
            for item in data.get("results", [])
        ]


class SerperProvider:
    def __init__(self, api_key: str):
        self._api_key = api_key

    async def search(self, query: str, k: int = 5) -> list[SearchResult]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": self._api_key},
                json={"q": query, "num": k},
            )
            resp.raise_for_status()
            data = resp.json()
        return [
            SearchResult(
                title=item.get("title", ""),
                url=item.get("link", ""),
                snippet=item.get("snippet", ""),
            )
            for item in data.get("organic", [])
        ]


class BraveSearchProvider:
    def __init__(self, api_key: str):
        self._api_key = api_key

    async def search(self, query: str, k: int = 5) -> list[SearchResult]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"X-Subscription-Token": self._api_key},
                params={"q": query, "count": k},
            )
            resp.raise_for_status()
            data = resp.json()
        return [
            SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("description", ""),
            )
            for item in data.get("web", {}).get("results", [])
        ]


class WebSearch:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._provider, self.provider_name = self._resolve_provider()

    @property
    def provider(self) -> WebSearchProvider | None:
        return self._provider

    def _resolve_provider(self) -> tuple[WebSearchProvider | None, str | None]:
        order = [p.strip() for p in self.settings.search_provider_order.split(",")]
        mapping: dict[str, tuple[str | None, type | None]] = {
            "tavily": (self.settings.tavily_api_key, TavilyProvider),
            "serper": (self.settings.serper_api_key, SerperProvider),
            "brave": (self.settings.brave_search_api_key, BraveSearchProvider),
        }
        for name in order:
            key, cls = mapping.get(name, (None, None))
            if key and cls:
                return cls(key), name
        return None, None

    async def search(self, query: str, k: int = 5) -> tuple[list[SearchResult], str | None]:
        if self._provider is None:
            return [], "未配置搜索 API，请在 backend/.env 中设置 TAVILY_API_KEY 等"
        results = await self._provider.search(query, k=k)
        return results, None
