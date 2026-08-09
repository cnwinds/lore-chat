from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

import httpx
import trafilatura

from app.engine.web.limits import (
    FETCH_URL_PDF_MAX_BYTES,
    FETCH_URL_PDF_TIMEOUT_FLOOR,
)
from app.index.extract import extract_text_from_bytes


@dataclass
class FetchResult:
    url: str
    title: str = ""
    markdown: str = ""
    snippet: str = ""
    error: str | None = None


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
    """将 HTML 转为干净 Markdown，优先提取正文，过滤导航/页脚等噪音。"""
    markdown = trafilatura.extract(
        html,
        url=url or None,
        output_format="markdown",
        include_links=True,
        include_tables=True,
        favor_precision=True,
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


def title_from_url(url: str) -> str:
    name = unquote((urlparse(url).path or "").rsplit("/", 1)[-1]).strip()
    return name or url


class WebFetcher:
    def __init__(
        self,
        timeout: int = 15,
        max_bytes: int = 102400,
        pdf_max_bytes: int = FETCH_URL_PDF_MAX_BYTES,
    ):
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.pdf_max_bytes = pdf_max_bytes

    def _request_timeout(self) -> int:
        # 响应头/魔数才知 PDF；下载前统一给足下限，避免大 PDF 被 HTML 超时掐断
        return max(self.timeout, FETCH_URL_PDF_TIMEOUT_FLOOR)

    async def fetch(self, url: str) -> FetchResult:
        if not is_safe_url(url):
            return FetchResult(url=url, error=_unsafe_reason(url))
        prefer_pdf = url_looks_like_pdf(url)
        try:
            async with httpx.AsyncClient(
                timeout=self._request_timeout(),
                follow_redirects=True,
                headers={"User-Agent": "LorechatBot/1.0"},
            ) as client:
                async with client.stream("GET", url) as resp:
                    resp.raise_for_status()
                    encoding = resp.encoding
                    content, is_pdf, err = await self._read_body(
                        resp, prefer_pdf=prefer_pdf
                    )
            if err:
                return FetchResult(url=url, error=err)
            if is_pdf:
                return self._result_from_pdf(url, content)
            html = content.decode(encoding or "utf-8", errors="replace")
            markdown = html_to_markdown(html, url)
            title = extract_page_title(html, content) or url
            snippet = markdown[:300].strip()
            return FetchResult(url=url, title=title, markdown=markdown, snippet=snippet)
        except Exception as e:
            return FetchResult(url=url, error=f"抓取失败: {e}")

    async def _read_body(
        self,
        resp: httpx.Response,
        *,
        prefer_pdf: bool,
    ) -> tuple[bytes, bool, str | None]:
        ctype = resp.headers.get("content-type", "")
        is_pdf = prefer_pdf or content_type_is_pdf(ctype)
        limit = self.pdf_max_bytes if is_pdf else self.max_bytes
        cl_header = resp.headers.get("content-length")
        cl = int(cl_header) if cl_header and cl_header.isdigit() else None
        # 仅在已判定为 PDF 时按 Content-Length 拒收；未标明的大 PDF 靠魔数升级限额
        if is_pdf and cl is not None and cl > limit:
            return b"", True, f"PDF过大（{cl} 字节，上限 {limit}）"

        chunks: list[bytes] = []
        total = 0
        async for chunk in resp.aiter_bytes():
            if not chunks and not is_pdf and chunk.startswith(_PDF_MAGIC):
                is_pdf = True
                limit = self.pdf_max_bytes
                if cl is not None and cl > limit:
                    return b"", True, f"PDF过大（{cl} 字节，上限 {limit}）"
            total += len(chunk)
            if total > limit:
                if is_pdf:
                    return b"", True, f"PDF过大（超过 {limit} 字节上限）"
                # HTML：截断后仍尽量抽正文（保持原行为）
                remain = limit - (total - len(chunk))
                if remain > 0:
                    chunks.append(chunk[:remain])
                break
            chunks.append(chunk)
        return b"".join(chunks), is_pdf, None

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
