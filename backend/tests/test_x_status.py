"""X / Twitter status URL + FxEmbed 解析。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.engine.web.fetcher import WebFetcher
from app.engine.web.x_status import (
    FXEMBED_STATUS_API,
    parse_fxembed_payload,
    parse_x_status_id,
    tweet_to_markdown,
)


class _AsyncClientStub:
    """httpx.AsyncClient 替身：子类实现 get / stream。"""

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None


class _HtmlStream:
    def __init__(self, content: bytes):
        self.status_code = 200
        self.headers = {"content-type": "text/html"}
        self.encoding = "utf-8"
        self._content = content

    def raise_for_status(self):
        return None

    async def aiter_bytes(self):
        yield self._content

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None


def test_parse_x_status_id_from_common_hosts():
    tid = "2083177530287353961"
    assert parse_x_status_id(f"https://x.com/HelloVyom/status/{tid}") == tid
    assert parse_x_status_id(f"https://twitter.com/a/status/{tid}?s=20") == tid
    assert parse_x_status_id(f"https://mobile.twitter.com/a/statuses/{tid}") == tid
    assert parse_x_status_id(f"https://www.x.com/a/status/{tid}") == tid


def test_parse_x_status_id_rejects_non_status_and_mirror_hosts():
    assert parse_x_status_id("https://x.com/HelloVyom") is None
    assert parse_x_status_id("https://example.com/status/12345") is None
    assert parse_x_status_id("https://x.com/search?q=status") is None
    # 镜像站不走专用路径（避免范围膨胀）
    assert parse_x_status_id("https://fxtwitter.com/i/status/2083177530287353961") is None


def test_tweet_to_markdown_marks_unofficial_embed():
    tweet = {
        "text": "hello world",
        "url": "https://x.com/u/status/1",
        "created_at": "Fri Jul 31 13:06:41 +0000 2026",
        "author": {"name": "Vyom", "screen_name": "HelloVyom"},
        "quote": {
            "text": "quoted body",
            "url": "https://x.com/u/status/2",
            "author": {"screen_name": "other"},
        },
        "media": {"all": [{"url": "https://pbs.twimg.com/media/x.jpg"}]},
    }
    result = tweet_to_markdown(tweet, original_url="https://x.com/u/status/1")
    assert result.error is None
    assert "HelloVyom" in result.title
    assert "hello world" in result.markdown
    assert "quoted body" in result.markdown
    assert "@other" in result.markdown
    assert "pbs.twimg.com" in result.markdown
    assert "unofficial embed" in result.markdown.lower()
    assert "official X API" in result.markdown
    assert "hello world" in result.snippet


def test_parse_fxembed_payload_requires_tweet_body():
    assert (
        parse_fxembed_payload({"code": 200}, original_url="https://x.com/a/status/1")
        is None
    )
    ok = parse_fxembed_payload(
        {
            "code": 200,
            "tweet": {
                "text": "hi",
                "url": "https://x.com/a/status/1",
                "author": {"screen_name": "a"},
            },
        },
        original_url="https://x.com/a/status/1",
    )
    assert ok is not None
    assert "hi" in ok.markdown


@pytest.mark.asyncio
async def test_fetch_x_status_uses_fxembed_before_html():
    tid = "2083177530287353961"
    url = f"https://x.com/HelloVyom/status/{tid}"
    payload = {
        "code": 200,
        "message": "OK",
        "tweet": {
            "text": "690 million tokens",
            "url": url,
            "author": {"name": "Vyom", "screen_name": "HelloVyom"},
        },
    }
    seen: list[str] = []

    class _Client(_AsyncClientStub):
        async def get(self, api_url):
            seen.append(api_url)

            class _Resp:
                status_code = 200

                def json(self):
                    return payload

            return _Resp()

        def stream(self, *a, **kw):
            raise AssertionError("HTML path must not run when FxEmbed succeeds")

    f = WebFetcher(timeout=5, max_bytes=10000)
    with patch("app.engine.web.x_status.httpx.AsyncClient", _Client):
        with patch("app.engine.web.fetcher.httpx.AsyncClient", _Client):
            result = await f.fetch(url)
    assert result.error is None, result.error
    assert seen == [FXEMBED_STATUS_API.format(status_id=tid)]
    assert "690 million tokens" in result.markdown
    assert "unofficial embed" in result.markdown.lower()


@pytest.mark.asyncio
async def test_fetch_x_status_falls_back_to_html_on_transport_error():
    tid = "2083177530287353961"
    url = f"https://x.com/HelloVyom/status/{tid}"
    html = (
        b"<html><head><title>Tweet</title></head>"
        b"<body><article><p>fallback body</p></article></body></html>"
    )

    class _Client(_AsyncClientStub):
        async def get(self, api_url):
            raise TimeoutError("embed down")

        def stream(self, method, u):
            return _HtmlStream(html)

    f = WebFetcher(timeout=5, max_bytes=10000)
    with patch("app.engine.web.x_status.httpx.AsyncClient", _Client):
        with patch("app.engine.web.fetcher.httpx.AsyncClient", _Client):
            result = await f.fetch(url)
    assert result.error is None, result.error
    assert "fallback body" in result.markdown


@pytest.mark.asyncio
async def test_fetch_x_status_miss_does_not_fallback_html():
    """私密/已删：embed 语义失败，不得再直连 HTML（避免空耗超时）。"""
    tid = "2083177530287353961"
    url = f"https://x.com/HelloVyom/status/{tid}"

    class _Client(_AsyncClientStub):
        async def get(self, api_url):
            class _Resp:
                status_code = 404

                def json(self):
                    return {"code": 404, "message": "Not Found"}

            return _Resp()

        def stream(self, *a, **kw):
            raise AssertionError("must not fall back to HTML on semantic miss")

    f = WebFetcher(timeout=5, max_bytes=10000)
    with patch("app.engine.web.x_status.httpx.AsyncClient", _Client):
        with patch("app.engine.web.fetcher.httpx.AsyncClient", _Client):
            result = await f.fetch(url)
    assert result.error is not None
    assert "不可访问" in result.error or "不存在" in result.error


@pytest.mark.asyncio
async def test_fetch_x_status_json_code_404_is_miss():
    tid = "1"
    url = "https://x.com/a/status/1"

    class _Client(_AsyncClientStub):
        async def get(self, api_url):
            class _Resp:
                status_code = 200

                def json(self):
                    return {"code": 404, "message": "Not Found"}

            return _Resp()

        def stream(self, *a, **kw):
            raise AssertionError("must not fall back to HTML on JSON 404")

    f = WebFetcher(timeout=5, max_bytes=10000)
    with patch("app.engine.web.x_status.httpx.AsyncClient", _Client):
        result = await f.fetch(url)
    assert result.error is not None
