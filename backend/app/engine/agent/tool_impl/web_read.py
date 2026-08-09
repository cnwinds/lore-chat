from __future__ import annotations

from app.engine.disclosure import (
    DEEP_DISCLOSURE_CHARS,
    MAX_DISCLOSURE_CHARS,
    disclose,
    disclosure_summary,
    resolve_disclosure_limit_from_args,
)


class WebReadTools:
    def __init__(
        self,
        *,
        fetcher,
        web_search,
        disclosure_chars: int,
        disclosure_deep_chars: int = DEEP_DISCLOSURE_CHARS,
        disclosure_max_chars: int = MAX_DISCLOSURE_CHARS,
    ) -> None:
        self.fetcher = fetcher
        self.searcher = web_search
        self.disclosure_chars = disclosure_chars
        self.disclosure_deep_chars = disclosure_deep_chars
        self.disclosure_max_chars = disclosure_max_chars
        self._fetch_cache: dict[str, object] = {}

    async def fetch_url(self, args: dict) -> dict:
        url = args["url"]
        result = self._fetch_cache.get(url)
        if result is None:
            result = await self.fetcher.fetch(url)
            if not result.error:
                self._fetch_cache[url] = result
        if result.error:
            return {
                "summary": f"{url} — {result.error}",
                "sources": [],
                "error": result.error,
            }
        sources = [
            {
                "type": "web",
                "url": result.url,
                "title": result.title,
                "snippet": result.snippet,
            }
        ]
        offset = args.get("offset", 0)
        limit = resolve_disclosure_limit_from_args(
            args,
            default_chars=self.disclosure_chars,
            deep_chars=self.disclosure_deep_chars,
            max_chars=self.disclosure_max_chars,
        )
        info = disclose(
            result.markdown,
            offset=offset,
            limit=limit,
            with_outline=True,
            max_chars=self.disclosure_max_chars,
        )
        label = result.title or result.url
        out = {
            "summary": disclosure_summary(label, info),
            "sources": sources,
            "markdown": info["body"],
            "total_chars": info["total_chars"],
            "offset": info["offset"],
            "returned_chars": info["returned_chars"],
            "has_more": info["has_more"],
        }
        if "next_offset" in info:
            out["next_offset"] = info["next_offset"]
        if "outline" in info:
            out["outline"] = info["outline"]
        return out

    async def web_search(self, args: dict) -> dict:
        query = args["query"]
        k = args.get("k", 5)
        results, err = await self.searcher.search(query, k=k)
        if err:
            return {"summary": err, "sources": [], "error": err}
        provider = self.searcher.provider_name or "unknown"
        sources = [
            {
                "type": "search",
                "provider": provider,
                "url": r.url,
                "title": r.title,
                "snippet": r.snippet,
            }
            for r in results
        ]
        return {
            "summary": f"搜索到 {len(results)} 条结果",
            "sources": sources,
        }
