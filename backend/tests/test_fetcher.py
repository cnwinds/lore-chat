from pathlib import Path
from unittest.mock import patch

import pytest

from app.engine.web.fetcher import (
    WebFetcher,
    content_type_is_pdf,
    content_type_is_plain_text,
    html_to_markdown,
    is_safe_url,
    title_from_url,
    url_looks_like_pdf,
)
from app.engine.web.limits import (
    FETCH_URL_HTML_MAX_BYTES,
    FETCH_URL_PDF_TIMEOUT_FLOOR,
)
from app.index.extract import BytesExtractResult

_FIXTURE_PDF = Path(__file__).parent / "fixtures" / "dummy.pdf"


def test_html_max_bytes_covers_css_heavy_news_pages():
    """旧 100KiB 上限会截断 TechCrunch 等站的正文区。"""
    assert FETCH_URL_HTML_MAX_BYTES >= 512 * 1024


def test_html_to_markdown_empty_when_body_cut_by_100kib_cap():
    """模拟 CSS/脚本在前、正文在后：截到 100KiB 后抽正文为空。"""
    style = "x" * 120_000
    article = (
        "<article><h1>Watermark</h1>"
        "<p>Anthropic published details about SynthID-Text watermarks on Claude.</p>"
        "</article>"
    )
    html = (
        f"<html><head><title>Watermark | News</title>"
        f"<style>{style}</style></head><body>{article}</body></html>"
    )
    assert "SynthID-Text" in html_to_markdown(html)
    truncated = html[:102400]
    assert "SynthID-Text" not in truncated
    assert html_to_markdown(truncated) == ""


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


def test_html_to_markdown_keeps_code_in_copy_chrome():
    """文档站常见：复制按钮 + 多层 div 包住 <pre>；勿因精度模式丢掉命令。"""
    html = """<html><body><main><div class="prose">
    <h1>Installation</h1>
    <p>Install with a single command:</p>
    <div class="mb-4"><div class="border group"><div class="relative">
    <button type="button">Copy</button>
    <div><pre class="w-full"><code>curl https://example.com/install | bash</code></pre></div>
    </div></div></div>
    <p>Then verify:</p>
    <div class="mb-4"><div class="border group"><div class="relative">
    <button type="button">Copy</button>
    <pre><code>tool --version</code></pre>
    </div></div></div>
    </div></main></body></html>"""
    md = html_to_markdown(html)
    assert "curl https://example.com/install" in md
    assert "tool --version" in md


def test_url_and_content_type_pdf_helpers():
    assert url_looks_like_pdf("https://ex.com/a/Rules%20V1.pdf?x=1") is True
    assert url_looks_like_pdf("https://ex.com/page") is False
    assert content_type_is_pdf("application/pdf; charset=binary") is True
    assert title_from_url("https://ex.com/docs/手册.pdf") == "手册.pdf"


class _FakeStreamResp:
    def __init__(self, content: bytes, headers: dict | None = None, encoding: str = "utf-8"):
        self.status_code = 200
        self.headers = headers or {"content-type": "text/html"}
        self.encoding = encoding
        self._content = content

    def raise_for_status(self):
        return None

    async def aiter_bytes(self):
        # 分两块，覆盖流式拼装与 PDF magic 检测
        mid = max(1, len(self._content) // 2)
        yield self._content[:mid]
        if mid < len(self._content):
            yield self._content[mid:]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


class _FakeClient:
    last_timeout: object | None = None

    def __init__(self, *args, **kwargs):
        self._resp = kwargs.pop("_resp")
        _FakeClient.last_timeout = kwargs.get("timeout")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def stream(self, method, url):
        return self._resp


def _patch_client(resp: _FakeStreamResp):
    def _client(*args, **kwargs):
        return _FakeClient(*args, _resp=resp, **kwargs)

    return patch("app.engine.web.fetcher.httpx.AsyncClient", _client)


@pytest.mark.asyncio
async def test_fetch_default_limit_keeps_body_after_large_head_boilerplate():
    """默认 HTML 上限须容纳头部长样板 + 正文（回归：TechCrunch 类页面抽空）。"""
    style = "x" * 120_000
    body = (
        f"<html><head><title>Watermark | News</title><style>{style}</style></head>"
        "<body><article><h1>Watermark</h1>"
        "<p>Anthropic published details about SynthID-Text watermarks on Claude.</p>"
        "</article></body></html>"
    ).encode()
    assert len(body) > 102400
    f = WebFetcher(timeout=5)  # 使用 FETCH_URL_HTML_MAX_BYTES 默认
    with _patch_client(_FakeStreamResp(body, {"content-type": "text/html"})):
        result = await f.fetch("https://example.com/news/watermark")
    assert result.error is None, result.error
    assert "SynthID-Text" in result.markdown
    assert result.title.startswith("Watermark")


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
    with _patch_client(_FakeStreamResp(html, {"content-type": "text/html"})):
        result = await f.fetch("https://example.com/page")
    assert result.error is None
    assert result.title == "Test"
    assert "Hello world" in result.markdown


def test_content_type_is_plain_text():
    assert content_type_is_plain_text("text/plain; charset=utf-8") is True
    assert content_type_is_plain_text("text/markdown") is True
    assert content_type_is_plain_text("text/html; charset=utf-8") is False


@pytest.mark.asyncio
async def test_fetch_plain_text_skips_trafilatura():
    """raw.githubusercontent.com 等返回 text/plain；勿经 HTML 抽取变成空串。"""
    raw = b"# Lore Chat\n\nA knowledge base assistant.\n"
    f = WebFetcher(timeout=5, max_bytes=10000)
    with _patch_client(
        _FakeStreamResp(raw, {"content-type": "text/plain; charset=utf-8"})
    ):
        result = await f.fetch(
            "https://raw.githubusercontent.com/cnwinds/lore-chat/master/README.md"
        )
    assert result.error is None, result.error
    assert "Lore Chat" in result.markdown
    assert "knowledge base" in result.markdown
    assert result.title.endswith("README.md")


@pytest.mark.asyncio
async def test_fetch_applies_timeout_floor():
    html = b"<html><body><p>x</p></body></html>"
    f = WebFetcher(timeout=5, max_bytes=10000)
    with _patch_client(_FakeStreamResp(html)):
        await f.fetch("https://example.com/page")
    assert _FakeClient.last_timeout == max(5, FETCH_URL_PDF_TIMEOUT_FLOOR)


@pytest.mark.asyncio
async def test_fetch_pdf_extracts_text():
    data = _FIXTURE_PDF.read_bytes()
    f = WebFetcher(timeout=5, max_bytes=1000, pdf_max_bytes=50_000)
    with _patch_client(
        _FakeStreamResp(data, {"content-type": "application/pdf"})
    ):
        result = await f.fetch("https://example.com/docs/dummy.pdf")
    assert result.error is None, result.error
    assert "Dummy PDF" in result.markdown
    assert result.title == "dummy.pdf"


@pytest.mark.asyncio
async def test_fetch_pdf_by_content_type_without_pdf_suffix(monkeypatch):
    """无 .pdf 后缀时靠 Content-Type 识别，且走 PDF 限额（不被 HTML 100KB 截断）。"""
    seen: dict = {}

    def _extract(data: bytes, *, file_extension: str):
        seen["nbytes"] = len(data)
        return BytesExtractResult(text=" substantive rules " * 2000)

    monkeypatch.setattr("app.engine.web.fetcher.extract_text_from_bytes", _extract)
    body = b"%PDF-" + b"R" * 150_000
    f = WebFetcher(timeout=5, max_bytes=1000, pdf_max_bytes=500_000)
    with _patch_client(
        _FakeStreamResp(body, {"content-type": "application/pdf"})
    ):
        result = await f.fetch("https://cdn.example.com/download?id=1")
    assert result.error is None, result.error
    assert seen["nbytes"] == len(body)
    assert len(result.markdown) > 10_000


@pytest.mark.asyncio
async def test_fetch_pdf_magic_upgrades_html_labelled_body(monkeypatch):
    """Content-Type 误标 HTML 时，魔数升级为 PDF 限额。"""
    seen: dict = {}

    def _extract(data: bytes, *, file_extension: str):
        seen["nbytes"] = len(data)
        return BytesExtractResult(text="ok")

    monkeypatch.setattr("app.engine.web.fetcher.extract_text_from_bytes", _extract)
    body = b"%PDF-" + b"y" * 80_000
    f = WebFetcher(timeout=5, max_bytes=1000, pdf_max_bytes=200_000)
    with _patch_client(_FakeStreamResp(body, {"content-type": "text/html"})):
        result = await f.fetch("https://example.com/rules")
    assert result.error is None, result.error
    assert seen["nbytes"] == len(body)


@pytest.mark.asyncio
async def test_fetch_pdf_rejects_oversize_by_content_length():
    f = WebFetcher(timeout=5, max_bytes=1000, pdf_max_bytes=1000)
    resp = _FakeStreamResp(
        b"%PDF-1.4 truncated",
        {"content-type": "application/pdf", "content-length": "999999"},
    )
    with _patch_client(resp):
        result = await f.fetch("https://example.com/big.pdf")
    assert result.error is not None
    assert "过大" in result.error


@pytest.mark.asyncio
async def test_fetch_pdf_empty_text_is_error(monkeypatch):
    f = WebFetcher(timeout=5, max_bytes=1000, pdf_max_bytes=50_000)
    blob = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\ntrailer\n%%EOF\n"
    monkeypatch.setattr(
        "app.engine.web.fetcher.extract_text_from_bytes",
        lambda data, file_extension: BytesExtractResult(text=""),
    )
    with _patch_client(
        _FakeStreamResp(blob, {"content-type": "application/pdf"})
    ):
        result = await f.fetch("https://example.com/scan.pdf")
    assert result.error is not None
    assert "未能解析出文本" in result.error


@pytest.mark.asyncio
async def test_fetch_truncated_empty_extract_is_error():
    """头部长样板导致截断后抽空：须报错，不能假装成功返回 0 字。"""
    style = "x" * 80_000
    body = (
        f"<html><head><title>Watermark | News</title><style>{style}</style></head>"
        "<body><article><p>Anthropic SynthID-Text details here.</p></article>"
        "</body></html>"
    ).encode()
    f = WebFetcher(timeout=5, max_bytes=40_000)
    with _patch_client(_FakeStreamResp(body, {"content-type": "text/html"})):
        result = await f.fetch("https://example.com/news/watermark")
    assert result.error is not None
    assert "截断" in result.error
    assert result.markdown == ""


@pytest.mark.asyncio
async def test_fetch_empty_shell_html_is_error_after_retry():
    shell = (
        b"<html><head><title>Empty Shell</title></head>"
        b"<body><div id='app'></div></body></html>"
    )
    f = WebFetcher(timeout=5, max_bytes=100_000)
    with _patch_client(_FakeStreamResp(shell, {"content-type": "text/html"})):
        result = await f.fetch("https://example.com/spa")
    assert result.error is not None
    assert "未能抽取正文" in result.error


@pytest.mark.asyncio
async def test_fetch_url_tool_does_not_cache_empty_markdown():
    from app.engine.agent.tool_impl.web_read import WebReadTools
    from app.engine.web.types import FetchResult

    class _SeqFetcher:
        def __init__(self):
            self.calls = 0

        async def fetch(self, url: str) -> FetchResult:
            self.calls += 1
            if self.calls == 1:
                return FetchResult(url=url, title="T", markdown="", snippet="")
            return FetchResult(
                url=url,
                title="T",
                markdown="# Hello body",
                snippet="Hello body",
            )

    fetcher = _SeqFetcher()
    tools = WebReadTools(fetcher=fetcher, web_search=None)
    first = await tools.fetch_url({"url": "https://example.com/a"})
    assert first.get("error")
    assert "https://example.com/a" not in tools._fetch_cache
    assert fetcher.calls == 1

    second = await tools.fetch_url({"url": "https://example.com/a"})
    assert fetcher.calls == 2
    assert not second.get("error")
    assert "Hello body" in (second.get("markdown") or "")
    assert "https://example.com/a" in tools._fetch_cache

    third = await tools.fetch_url({"url": "https://example.com/a"})
    assert fetcher.calls == 2  # cache hit
    assert "Hello body" in (third.get("markdown") or "")
