from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
import trafilatura


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


class WebFetcher:
    def __init__(self, timeout: int = 15, max_bytes: int = 102400):
        self.timeout = timeout
        self.max_bytes = max_bytes

    async def fetch(self, url: str) -> FetchResult:
        if not is_safe_url(url):
            return FetchResult(url=url, error=_unsafe_reason(url))
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": "LorechatBot/1.0"},
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                content = resp.content[: self.max_bytes]
            html = content.decode(resp.encoding or "utf-8", errors="replace")
            markdown = html_to_markdown(html, url)
            title = extract_page_title(html, content) or url
            snippet = markdown[:300].strip()
            return FetchResult(url=url, title=title, markdown=markdown, snippet=snippet)
        except Exception as e:
            return FetchResult(url=url, error=f"抓取失败: {e}")


def _extract_title(content: bytes) -> str:
    m = re.search(rb"<title[^>]*>([^<]+)</title>", content, re.I)
    return m.group(1).decode("utf-8", errors="replace").strip() if m else ""
