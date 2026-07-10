from __future__ import annotations

import ipaddress
import os
import re
import socket
import tempfile
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from markitdown import MarkItDown


@dataclass
class FetchResult:
    url: str
    title: str = ""
    markdown: str = ""
    snippet: str = ""
    error: str | None = None


def is_safe_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname
    if not host or host in ("localhost",):
        return False
    try:
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False
    except socket.gaierror:
        return False
    return True


class WebFetcher:
    def __init__(self, timeout: int = 15, max_bytes: int = 102400):
        self.timeout = timeout
        self.max_bytes = max_bytes
        self._md = MarkItDown()

    async def fetch(self, url: str) -> FetchResult:
        if not is_safe_url(url):
            return FetchResult(url=url, error="拒绝访问私有或本地地址")
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": "LorechatBot/1.0"},
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                content = resp.content[: self.max_bytes]
            suffix = ".html" if b"<html" in content[:200].lower() else ".txt"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                md_result = self._md.convert(tmp_path)
                markdown = md_result.text_content or ""
            finally:
                os.unlink(tmp_path)
            title = _extract_title(content) or url
            snippet = markdown[:300].strip()
            return FetchResult(url=url, title=title, markdown=markdown, snippet=snippet)
        except Exception as e:
            return FetchResult(url=url, error=f"抓取失败: {e}")


def _extract_title(content: bytes) -> str:
    m = re.search(rb"<title[^>]*>([^<]+)</title>", content, re.I)
    return m.group(1).decode("utf-8", errors="replace").strip() if m else ""
