"""知识库 Markdown 插图路径：存储侧禁止残留 /api/download 等 API 绝对链。"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse

_MD_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def _path_from_download_url(src: str) -> str | None:
    raw = (src or "").strip()
    if not raw or "/api/download" not in raw:
        return None
    try:
        u = urlparse(raw if "://" in raw else f"http://local.invalid{raw}")
        if u.path.rstrip("/").endswith("/api/download") or "/api/download" in u.path:
            qs = parse_qs(u.query)
            vals = qs.get("path") or []
            if vals and vals[0]:
                return unquote(vals[0])
    except Exception:
        pass
    m = re.search(r"[?&]path=([^&]+)", raw)
    if m:
        try:
            return unquote(m.group(1))
        except Exception:
            return m.group(1)
    return None


def sanitize_markdown_image_srcs_for_storage(md: str) -> str:
    """把展示期 download URL 还原为相对路径；仍含 /api/download 则报错。"""
    if not md or "![" not in md:
        return md

    def repl(m: re.Match[str]) -> str:
        alt, src = m.group(1), m.group(2).strip()
        path = _path_from_download_url(src)
        if path is not None:
            return f"![{alt}]({path})"
        if "/api/download" in src or "/api/attachments/signed/" in src:
            raise ValueError(
                "知识库正文禁止写入 /api/download 或签名附件绝对 URL，请使用相对路径"
            )
        return m.group(0)

    return _MD_IMAGE.sub(repl, md)
