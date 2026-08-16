from __future__ import annotations

import ipaddress
import logging
import re
from urllib.parse import unquote, urlparse

import httpx
import trafilatura

from app.engine.web.limits import (
    FETCH_URL_HTML_MAX_BYTES,
    FETCH_URL_PDF_MAX_BYTES,
    FETCH_URL_PDF_TIMEOUT_FLOOR,
)
from app.engine.web.types import FetchResult
from app.engine.web.weixin_article import (
    WEIXIN_HTML_MAX_BYTES,
    extract_weixin_js_content_html,
    is_weixin_article_url,
    looks_like_weixin_challenge,
    weixin_js_content_to_markdown,
    weixin_request_headers,
)
from app.engine.web.x_status import fetch_status_via_fxembed, parse_x_status_id
from app.index.extract import extract_text_from_bytes

# 兼容旧导入路径
__all__ = [
    "FetchResult",
    "WebFetcher",
    "content_type_is_pdf",
    "extract_page_title",
    "html_to_markdown",
    "is_safe_url",
    "title_from_url",
    "url_looks_like_pdf",
]

_log = logging.getLogger(__name__)

_BLOCKED_HOSTS = frozenset({
    "localhost",
    "metadata.google.internal",
    "metadata.goog",
})

_PDF_MAGIC = b"%PDF-"


def is_safe_url(url: str) -> bool:
    """SSRF 防护：拒绝内网 IP 字面量与本地主机名；域名不预解析 DNS。

    说明：Clash 等代理的 fake-ip（198.18.x.x）会在 DNS 阶段返回私网地址，
    若据此拦截会导致 github.com 等外站无法抓取。域名交由 httpx 走系统代理访问。
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        return False
    if host in _BLOCKED_HOSTS or host.endswith(".localhost"):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
    )


def _unsafe_reason(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    return f"拒绝访问私有或本地地址：{host}（{url}）"


def html_to_markdown(html: str, url: str = "") -> str:
    """将 HTML 转为干净 Markdown，优先提取正文，过滤导航/页脚等噪音。

    不用 favor_precision：精度模式几乎不额外去广告，却易丢掉文档站
    （如带复制按钮外壳的 <pre>）里的命令代码块。
    """
    markdown = trafilatura.extract(
        html,
        url=url or None,
        output_format="markdown",
        include_links=True,
        include_tables=True,
        favor_precision=False,
    )
    if markdown and markdown.strip():
        return markdown.strip()
    fallback = trafilatura.html2txt(html)
    return fallback.strip() if fallback else ""


def extract_page_title(html: str, raw: bytes) -> str:
    metadata = trafilatura.extract_metadata(html)
    if metadata and metadata.title:
        return metadata.title.strip()
    return _extract_title(raw)


def url_looks_like_pdf(url: str) -> bool:
    path = unquote(urlparse(url).path or "").lower()
    return path.endswith(".pdf")


def content_type_is_pdf(content_type: str) -> bool:
    return "application/pdf" in (content_type or "").lower()


# 非 HTML：走 trafilatura 会得到空串（如 raw.githubusercontent.com 的 README）
_PLAIN_TEXT_TYPES = frozenset({
    "text/plain",
    "text/markdown",
    "text/x-markdown",
    "text/csv",
    "text/tab-separated-values",
    "application/json",
    "application/ld+json",
    "application/xml",
    "text/xml",
    "application/yaml",
    "application/x-yaml",
    "text/yaml",
})


def content_type_is_plain_text(content_type: str) -> bool:
    ctype = (content_type or "").lower().split(";", 1)[0].strip()
    return ctype in _PLAIN_TEXT_TYPES


def title_from_url(url: str) -> str:
    name = unquote((urlparse(url).path or "").rsplit("/", 1)[-1]).strip()
    return name or url


class WebFetcher:
    def __init__(
        self,
        timeout: int = 15,
        max_bytes: int = FETCH_URL_HTML_MAX_BYTES,
        pdf_max_bytes: int = FETCH_URL_PDF_MAX_BYTES,
    ):
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.pdf_max_bytes = pdf_max_bytes

    def _request_timeout(self) -> float:
        # 响应头/魔数才知 PDF；下载前统一给足下限，避免大 PDF 被 HTML 超时掐断
        return max(self.timeout, FETCH_URL_PDF_TIMEOUT_FLOOR)

    def _client(
        self,
        *,
        timeout: float,
        accept: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.AsyncClient:
        headers = {"User-Agent": "LorechatBot/1.0"}
        if accept:
            headers["Accept"] = accept
        if extra_headers:
            headers.update(extra_headers)
        return httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers=headers,
        )

    async def fetch(self, url: str) -> FetchResult:
        if not is_safe_url(url):
            return FetchResult(url=url, error=_unsafe_reason(url))
        status_id = parse_x_status_id(url)
        if status_id:
            embed = await fetch_status_via_fxembed(
                status_id, original_url=url, timeout=float(self.timeout)
            )
            if embed is not None:
                return embed
            _log.debug("X status embed unavailable; falling back to HTML url=%s", url)
        return await self._fetch_http(url)

    async def _fetch_http(self, url: str, *, attempt: int = 0) -> FetchResult:
        prefer_pdf = url_looks_like_pdf(url)
        weixin = is_weixin_article_url(url)
        extra = weixin_request_headers() if weixin else None
        html_limit = WEIXIN_HTML_MAX_BYTES if weixin else self.max_bytes
        try:
            async with self._client(
                timeout=self._request_timeout(),
                extra_headers=extra,
            ) as client:
                async with client.stream("GET", url) as resp:
                    resp.raise_for_status()
                    encoding = resp.encoding
                    ctype = resp.headers.get("content-type", "")
                    content, is_pdf, err, truncated = await self._read_body(
                        resp,
                        prefer_pdf=prefer_pdf,
                        html_max_bytes=html_limit,
                    )
            if err:
                return FetchResult(url=url, error=err)
            if is_pdf:
                return self._result_from_pdf(url, content)
            body = content.decode(encoding or "utf-8", errors="replace")
            if content_type_is_plain_text(ctype):
                text = body.strip()
                title = title_from_url(url)
                if not text:
                    return FetchResult(
                        url=url,
                        title=title,
                        error="页面无文本内容",
                    )
                return FetchResult(
                    url=url,
                    title=title,
                    markdown=text,
                    snippet=text[:300],
                )
            html = body
            if weixin and looks_like_weixin_challenge(html):
                return FetchResult(
                    url=url,
                    error="微信公众号返回验证页或未放行正文，请稍后重试或在微信内打开",
                )
            title = extract_page_title(html, content) or url
            if weixin:
                body_html = extract_weixin_js_content_html(html)
                if not body_html:
                    return FetchResult(
                        url=url,
                        title=title,
                        error=(
                            "微信公众号正文容器未抓到（页面过大被截断或结构变化），"
                            "请稍后重试或在微信内打开"
                        ),
                    )
                markdown = weixin_js_content_to_markdown(body_html, url)
            else:
                markdown = html_to_markdown(html, url)
            if not (markdown or "").strip():
                if truncated:
                    return FetchResult(
                        url=url,
                        title=title,
                        error=(
                            f"页面过大被截断（已读 {len(content)} 字节），未能抽取正文；"
                            "请换源或提高 FETCH_URL_MAX_BYTES"
                        ),
                    )
                if attempt < 1:
                    # 代理/链路偶发半包：重试一次再判定失败
                    _log.info(
                        "empty html extract, retrying url=%s bytes=%s",
                        url,
                        len(content),
                    )
                    return await self._fetch_http(url, attempt=attempt + 1)
                return FetchResult(
                    url=url,
                    title=title,
                    error=(
                        "未能抽取正文（可能是反爬壳页、脚本渲染或传输不完整），"
                        "请改用搜索或其他来源"
                    ),
                )
            snippet = markdown[:300].strip()
            return FetchResult(url=url, title=title, markdown=markdown, snippet=snippet)
        except Exception as e:
            return FetchResult(url=url, error=f"抓取失败: {e}")

    async def _read_body(
        self,
        resp: httpx.Response,
        *,
        prefer_pdf: bool,
        html_max_bytes: int | None = None,
    ) -> tuple[bytes, bool, str | None, bool]:
        ctype = resp.headers.get("content-type", "")
        is_pdf = prefer_pdf or content_type_is_pdf(ctype)
        html_cap = html_max_bytes if html_max_bytes is not None else self.max_bytes
        limit = self.pdf_max_bytes if is_pdf else html_cap
        cl_header = resp.headers.get("content-length")
        cl = int(cl_header) if cl_header and cl_header.isdigit() else None
        # 仅在已判定为 PDF 时按 Content-Length 拒收；未标明的大 PDF 靠魔数升级限额
        if is_pdf and cl is not None and cl > limit:
            return b"", True, f"PDF过大（{cl} 字节，上限 {limit}）", False

        chunks: list[bytes] = []
        total = 0
        truncated = False
        async for chunk in resp.aiter_bytes():
            if not chunks and not is_pdf and chunk.startswith(_PDF_MAGIC):
                is_pdf = True
                limit = self.pdf_max_bytes
                if cl is not None and cl > limit:
                    return b"", True, f"PDF过大（{cl} 字节，上限 {limit}）", False
            total += len(chunk)
            if total > limit:
                if is_pdf:
                    return b"", True, f"PDF过大（超过 {limit} 字节上限）", False
                # HTML：截断后仍尽量抽正文（保持原行为）
                remain = limit - (total - len(chunk))
                if remain > 0:
                    chunks.append(chunk[:remain])
                truncated = True
                break
            chunks.append(chunk)
        return b"".join(chunks), is_pdf, None, truncated

    def _result_from_pdf(self, url: str, content: bytes) -> FetchResult:
        extracted = extract_text_from_bytes(content, file_extension=".pdf")
        if extracted.error:
            return FetchResult(url=url, error=extracted.error)
        if not extracted.text:
            return FetchResult(
                url=url,
                error="PDF 未能解析出文本（可能是扫描件、加密或损坏）",
            )
        title = title_from_url(url)
        return FetchResult(
            url=url,
            title=title,
            markdown=extracted.text,
            snippet=extracted.text[:300].strip(),
        )


def _extract_title(content: bytes) -> str:
    m = re.search(rb"<title[^>]*>([^<]+)</title>", content, re.I)
    return m.group(1).decode("utf-8", errors="replace").strip() if m else ""
