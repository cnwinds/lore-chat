"""微信公众号单篇文章：直连常被 UA 风控拦成验证页。

根因：服务端检查 User-Agent 是否含 MicroMessenger；伪装微信客户端即可放行。
对标 x_status：站点特例藏在 WebFetcher 内，fetch_url 工具接口不变。
"""

from __future__ import annotations

from urllib.parse import urlparse

_WEIXIN_HOSTS = frozenset(
    {
        "mp.weixin.qq.com",
        "www.mp.weixin.qq.com",
        "mobile.mp.weixin.qq.com",
    }
)

# 会话实测可用的微信客户端 UA（含 MicroMessenger 关键字即可）
WEIXIN_CLIENT_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
    "MicroMessenger/8.0.49 NetType/WIFI Language/zh_CN"
)

# 公众号页脚本多，默认 HTML 限额易截断到 js_content 之前
WEIXIN_HTML_MAX_BYTES = 512 * 1024

# 拦截页特征：须配合「无正文容器」使用，避免正文 JS 里的「验证」误判
_CHALLENGE_MARKERS = (
    "环境异常",
    "完成验证",
    "去验证",
    "secitptpage",
    "wxa-captcha",
)


def is_weixin_article_url(url: str) -> bool:
    """是否为微信公众号单篇文章链接。"""
    parsed = urlparse((url or "").strip())
    host = (parsed.hostname or "").lower().rstrip(".")
    if host not in _WEIXIN_HOSTS:
        return False
    path = (parsed.path or "").rstrip("/")
    query = parsed.query or ""
    # /s/xxx（path 含 /s/）或 /s?__biz=...（path 为 /s 且有 query）
    if "/s/" in (parsed.path or "").lower():
        return True
    if path.lower() == "/s" and query:
        return True
    return False


def weixin_request_headers() -> dict[str, str]:
    return {
        "User-Agent": WEIXIN_CLIENT_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }


def looks_like_weixin_challenge(html: str) -> bool:
    """缺正文容器且出现拦截特征时返回 True（避免正文 JS 里「验证」误判）。"""
    if not html or "js_content" in html:
        return False
    lowered = html.lower()
    return any(marker.lower() in lowered for marker in _CHALLENGE_MARKERS)
