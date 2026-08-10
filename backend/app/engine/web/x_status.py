"""X / Twitter status：直连页面常超时或反爬，优先走公开 embed API。

根因：status 页依赖客户端渲染与风控，HTML 抓取不稳定；
公开 embed（FxEmbed）返回结构化 JSON，适合作为该类 URL 的专用路径。

返回约定（供 WebFetcher）：
- FetchResult 且无 error → 成功，勿再抓 HTML
- FetchResult 且有 error → 语义失败（私密/已删/不可解析），勿再抓 HTML
- None → 传输/服务不确定，可回退通用 HTML
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

import httpx

from app.engine.web.types import FetchResult

_log = logging.getLogger(__name__)

_STATUS_ID_RE = re.compile(r"/status(?:es)?/(\d{5,30})(?:/|$)", re.I)

_X_STATUS_HOSTS = frozenset(
    {
        "x.com",
        "www.x.com",
        "mobile.x.com",
        "twitter.com",
        "www.twitter.com",
        "mobile.twitter.com",
    }
)

FXEMBED_STATUS_API = "https://api.fxtwitter.com/status/{status_id}"

_MISS = "该 X 帖不存在或不可访问"


def parse_x_status_id(url: str) -> str | None:
    """若 URL 指向单条 X/Twitter status，返回数字 id；否则 None。"""
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower().rstrip(".")
    if host not in _X_STATUS_HOSTS:
        return None
    m = _STATUS_ID_RE.search(parsed.path or "")
    return m.group(1) if m else None


def _handle_and_text(obj: dict[str, Any]) -> tuple[str, str, str]:
    """返回 (handle, text, url)。"""
    author = obj.get("author") or {}
    screen = (author.get("screen_name") or "").strip()
    name = (author.get("name") or screen or "unknown").strip()
    handle = f"@{screen}" if screen else name
    text = (obj.get("text") or obj.get("raw_text") or "").strip()
    url = (obj.get("url") or "").strip()
    return handle, text, url


def tweet_to_markdown(tweet: dict[str, Any], *, original_url: str) -> FetchResult:
    """将 FxEmbed tweet 转为 FetchResult；正文标明非官方 embed。"""
    handle, text, post_url = _handle_and_text(tweet)
    post_url = post_url or original_url
    created = (tweet.get("created_at") or "").strip()
    title = f"{handle} on X" if handle else (text[:80] or post_url)

    lines = [
        f"# {handle}",
        "",
        f"- URL: {post_url}",
    ]
    if created:
        lines.append(f"- Posted: {created}")
    lines.extend(
        [
            "- Source: unofficial embed API (FxEmbed); not the official X API",
            "",
            text or "_(empty text)_",
        ]
    )

    quote = tweet.get("quote")
    if isinstance(quote, dict):
        q_handle, q_text, q_url = _handle_and_text(quote)
        if q_text:
            lines.extend(["", "## Quoted post", "", f"**{q_handle}**"])
            if q_url:
                lines.append(f"- URL: {q_url}")
            lines.extend(["", q_text])

    media_urls = _media_urls(tweet.get("media"))
    if media_urls:
        lines.extend(["", "## Media"])
        for u in media_urls:
            lines.append(f"- {u}")

    markdown = "\n".join(lines).strip() + "\n"
    snippet = (text or markdown)[:300].strip()
    return FetchResult(
        url=original_url, title=title, markdown=markdown, snippet=snippet
    )


def _media_urls(media: Any) -> list[str]:
    if not isinstance(media, dict):
        return []
    urls: list[str] = []
    for key in ("all", "videos"):
        for item in media.get(key) or []:
            if not isinstance(item, dict):
                continue
            u = (item.get("url") or item.get("thumbnail_url") or "").strip()
            if u and u not in urls:
                urls.append(u)
    return urls


def parse_fxembed_payload(
    data: dict[str, Any], *, original_url: str
) -> FetchResult | None:
    """解析已确认业务成功的 FxEmbed JSON；结构不可用时返回 None。"""
    if not isinstance(data, dict):
        return None
    tweet = data.get("tweet")
    if not isinstance(tweet, dict):
        return None
    _, text, _ = _handle_and_text(tweet)
    has_quote_text = False
    quote = tweet.get("quote")
    if isinstance(quote, dict):
        _, q_text, _ = _handle_and_text(quote)
        has_quote_text = bool(q_text)
    if not (text or has_quote_text or _media_urls(tweet.get("media"))):
        return None
    return tweet_to_markdown(tweet, original_url=original_url)


def _miss(original_url: str, detail: str = _MISS) -> FetchResult:
    return FetchResult(url=original_url, error=detail)


def _json_business_code(data: dict[str, Any]) -> int | None:
    code = data.get("code")
    if code is None:
        return None
    try:
        return int(code)
    except (TypeError, ValueError):
        return None


async def fetch_status_via_fxembed(
    status_id: str,
    *,
    original_url: str,
    timeout: float,
) -> FetchResult | None:
    """见模块文档的返回约定。"""
    api = FXEMBED_STATUS_API.format(status_id=status_id)
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": "LorechatBot/1.0",
                "Accept": "application/json",
            },
        ) as client:
            resp = await client.get(api)
    except Exception as e:
        _log.debug("FxEmbed transport failed id=%s: %s", status_id, e)
        return None

    if resp.status_code in (401, 403, 404):
        return _miss(original_url)
    if resp.status_code != 200:
        _log.debug(
            "FxEmbed HTTP %s id=%s — fallback HTML", resp.status_code, status_id
        )
        return None

    try:
        data = resp.json()
    except Exception as e:
        _log.debug("FxEmbed JSON failed id=%s: %s", status_id, e)
        return None

    if not isinstance(data, dict):
        return None

    code = _json_business_code(data)
    if code is not None:
        if code in (401, 403, 404):
            return _miss(original_url)
        if code != 200:
            if 400 <= code < 500:
                return _miss(original_url, f"{_MISS}（code={code}）")
            _log.debug("FxEmbed code=%s id=%s — fallback HTML", code, status_id)
            return None

    parsed = parse_fxembed_payload(data, original_url=original_url)
    if parsed is None:
        return _miss(original_url, "未能从 embed 解析该帖内容")
    return parsed
