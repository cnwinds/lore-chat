"""厂商 HTTP 附加头。与 /models 列表解析解耦，供 LLM 客户端与生图 adapter 共用。"""

from __future__ import annotations


def provider_extra_headers(base_url: str) -> dict[str, str]:
    """部分网关（如 OpenRouter）建议带应用标识，便于排行与排障。"""
    if "openrouter.ai" in (base_url or "").lower():
        return {
            "HTTP-Referer": "https://github.com/cnwinds/lore-chat",
            "X-Title": "Lore Chat",
        }
    return {}
