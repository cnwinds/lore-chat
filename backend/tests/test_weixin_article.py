"""微信公众号文章：URL 识别、UA、验证页与 WebFetcher 集成。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.engine.web.fetcher import WebFetcher
from app.engine.web.weixin_article import (
    WEIXIN_CLIENT_UA,
    is_weixin_article_url,
    looks_like_weixin_challenge,
    weixin_request_headers,
)


def test_is_weixin_article_url_accepts_common_forms():
    assert is_weixin_article_url(
        "https://mp.weixin.qq.com/s/6_-S0yIVlCtqW8U8JfwdGA"
        "?scene=1&click_id=1483083671"
    )
    assert is_weixin_article_url("https://mp.weixin.qq.com/s/abcdef")
    assert is_weixin_article_url(
        "https://mp.weixin.qq.com/s?__biz=MzA&mid=1&idx=1&sn=abc"
    )
    assert is_weixin_article_url("http://www.mp.weixin.qq.com/s/xyz")
    assert is_weixin_article_url("https://mobile.mp.weixin.qq.com/s/xyz")


def test_is_weixin_article_url_rejects_non_articles():
    assert not is_weixin_article_url("https://mp.weixin.qq.com/")
    assert not is_weixin_article_url("https://mp.weixin.qq.com/s")
    assert not is_weixin_article_url("https://example.com/s/foo")
    assert not is_weixin_article_url("https://weixin.qq.com/s/abc")


def test_weixin_headers_include_micromessenger():
    h = weixin_request_headers()
    assert "MicroMessenger" in h["User-Agent"]
    assert h["User-Agent"] == WEIXIN_CLIENT_UA


def test_looks_like_weixin_challenge():
    ok = (
        "<html><head><title>一文读懂</title></head>"
        '<body><div id="js_content"><p>正文</p></div>'
        "<script>需完成验证</script></body></html>"
    )
    assert looks_like_weixin_challenge(ok) is False

    challenge = (
        "<html><head><title></title></head>"
        "<body><p>环境异常，完成验证后即可继续访问</p></body></html>"
    )
    assert looks_like_weixin_challenge(challenge) is True

    # 缺 js_content 但无拦截特征（如截断页）→ 不按验证页误杀
    truncated = "<html><head><title></title></head><body><p>loading</p></body></html>"
    assert looks_like_weixin_challenge(truncated) is False
    assert looks_like_weixin_challenge("") is False
    assert looks_like_weixin_challenge('<div class="WXA-CAPTCHA">x</div>') is True


class _FakeStreamResp:
    def __init__(self, content: bytes, headers: dict | None = None):
        self.status_code = 200
        self.headers = headers or {"content-type": "text/html"}
        self.encoding = "utf-8"
        self._content = content

    def raise_for_status(self):
        return None

    async def aiter_bytes(self):
        yield self._content

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


class _CapturingClient:
    last_headers: dict | None = None

    def __init__(self, *args, **kwargs):
        self._resp = kwargs.pop("_resp")
        _CapturingClient.last_headers = dict(kwargs.get("headers") or {})

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def stream(self, method, url):
        return self._resp


def _patch_client(resp: _FakeStreamResp):
    def _client(*args, **kwargs):
        return _CapturingClient(*args, _resp=resp, **kwargs)

    return patch("app.engine.web.fetcher.httpx.AsyncClient", _client)


@pytest.mark.asyncio
async def test_fetch_weixin_uses_micromessenger_ua():
    html = (
        "<html><head><title>FDE</title></head>"
        '<body><div id="js_content"><p>Hello Weixin</p></div></body></html>'
    ).encode("utf-8")
    f = WebFetcher(timeout=5, max_bytes=10000)
    with _patch_client(_FakeStreamResp(html)):
        result = await f.fetch(
            "https://mp.weixin.qq.com/s/6_-S0yIVlCtqW8U8JfwdGA?scene=1"
        )
    assert not result.error
    assert "Hello Weixin" in (result.markdown or "")
    assert _CapturingClient.last_headers is not None
    assert "MicroMessenger" in _CapturingClient.last_headers.get("User-Agent", "")


@pytest.mark.asyncio
async def test_fetch_normal_site_keeps_lorechat_ua():
    html = b"<html><head><title>Ex</title></head><body><p>Hi</p></body></html>"
    f = WebFetcher(timeout=5, max_bytes=10000)
    with _patch_client(_FakeStreamResp(html)):
        result = await f.fetch("https://example.com/page")
    assert not result.error
    assert _CapturingClient.last_headers is not None
    assert _CapturingClient.last_headers.get("User-Agent") == "LorechatBot/1.0"


@pytest.mark.asyncio
async def test_fetch_weixin_challenge_returns_error():
    html = (
        "<html><head><title></title></head>"
        "<body><p>环境异常，完成验证后即可继续访问</p></body></html>"
    ).encode("utf-8")
    f = WebFetcher(timeout=5, max_bytes=10000)
    with _patch_client(_FakeStreamResp(html)):
        result = await f.fetch("https://mp.weixin.qq.com/s/blocked")
    assert result.error
    assert "验证" in result.error or "微信" in result.error
