import pytest
from unittest.mock import AsyncMock, patch

from app.engine.web.fetcher import (
    WebFetcher,
    html_to_markdown,
    is_safe_url,
)


def test_is_safe_url_rejects_localhost():
    assert is_safe_url("http://localhost/secret") is False
    assert is_safe_url("http://127.0.0.1/") is False


def test_is_safe_url_allows_public_hostnames():
    # 不因 DNS fake-ip（如 Clash 的 198.18.x.x）而拦截域名
    assert is_safe_url("https://github.com/cnwinds/lore-chat") is True
    assert is_safe_url("https://example.com/page") is True


def test_html_to_markdown_strips_boilerplate():
    html = """<html><head><title>Test</title></head><body>
    <nav><a href="/">Home</a></nav>
    <article><h1>Main</h1><p>Hello world</p></article>
    <footer>Copyright</footer>
    </body></html>"""
    md = html_to_markdown(html)
    assert "Hello world" in md
    assert "Copyright" not in md


@pytest.mark.asyncio
async def test_fetch_rejects_unsafe_url():
    f = WebFetcher(timeout=5, max_bytes=10000)
    result = await f.fetch("http://127.0.0.1/admin")
    assert result.error is not None
    assert "拒绝" in result.error or "unsafe" in result.error.lower()


@pytest.mark.asyncio
async def test_fetch_returns_markdown():
    html = b"<html><head><title>Test</title></head><body><p>Hello world</p></body></html>"
    f = WebFetcher(timeout=5, max_bytes=10000)
    with patch("app.engine.web.fetcher.httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.encoding = "utf-8"
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.content = html
        mock_resp.raise_for_status = lambda: None
        mock_get.return_value = mock_resp
        result = await f.fetch("https://example.com/page")
    assert result.error is None
    assert result.title == "Test"
    assert "Hello world" in result.markdown
