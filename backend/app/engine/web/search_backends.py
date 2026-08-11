"""各搜索厂商 HTTP 适配；供 resolve / WebSearch 共用。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

from app.engine.web.search_providers import SearchProviderEntry


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


_PROVIDER_CLS: dict[str, type] = {
    "tavily": TavilyProvider,
    "serper": SerperProvider,
    "brave": BraveSearchProvider,
}


def build_provider(entry: SearchProviderEntry) -> WebSearchProvider:
    cls = _PROVIDER_CLS[entry.provider]
    assert entry.api_key
    return cls(entry.api_key)
