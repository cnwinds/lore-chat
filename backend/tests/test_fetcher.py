from pathlib import Path
from unittest.mock import patch

import pytest

from app.engine.web.fetcher import (
    WebFetcher,
    content_type_is_pdf,
    html_to_markdown,
    is_safe_url,
    title_from_url,
    url_looks_like_pdf,
)
from app.engine.web.limits import FETCH_URL_PDF_TIMEOUT_FLOOR
from app.index.extract import BytesExtractResult

_FIXTURE_PDF = Path(__file__).parent / "fixtures" / "dummy.pdf"


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
async def test_fetch_pdf_converter_failure_is_distinct(monkeypatch):
    f = WebFetcher(timeout=5, max_bytes=1000, pdf_max_bytes=50_000)
    monkeypatch.setattr(
        "app.engine.web.fetcher.extract_text_from_bytes",
        lambda data, file_extension: BytesExtractResult(
            error="文档转换失败: boom"
        ),
    )
    with _patch_client(
        _FakeStreamResp(b"%PDF-1.4 x", {"content-type": "application/pdf"})
    ):
        result = await f.fetch("https://example.com/bad.pdf")
    assert result.error is not None
    assert "转换失败" in result.error
    assert "扫描件" not in result.error
