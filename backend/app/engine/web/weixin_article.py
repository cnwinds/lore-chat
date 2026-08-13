"""微信公众号单篇文章抓取特例。

根因两层：
1. UA：直连常被拦成验证页；请求须带 MicroMessenger。
2. 正文：页面前置大量脚本，`#js_content` 往往在数百 KB～1MB+ 之后；
   仅提高限额仍脆弱，应优先抽出该容器再转 Markdown。

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

# 兜底读入上限：须盖过常见「脚本前缀 + #js_content」；正文仍优先按容器抽取
WEIXIN_HTML_MAX_BYTES = 2 * 1024 * 1024

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


def extract_weixin_js_content_html(html: str) -> str | None:
    """抽出 `#js_content` 节点 HTML（含自身）；缺失或解析失败返回 None。"""
    if not html or "js_content" not in html:
        return None
    try:
        from lxml import html as lxml_html
    except ImportError:
        return None
    try:
        root = lxml_html.fromstring(html)
    except Exception:
        return None
    nodes = root.xpath('//*[@id="js_content"]')
    if not nodes:
        return None
    node = nodes[0]
    # 空壳（仅空白/脚本占位）视为未拿到正文
    text = (node.text_content() or "").strip()
    if not text:
        return None
    return lxml_html.tostring(node, encoding="unicode", method="html")


def weixin_js_content_to_markdown(body_html: str, url: str = "") -> str:
    """将 `#js_content` 片段转为 Markdown（包一层完整文档供抽取器解析）。"""
    # 延迟导入避免与 fetcher 循环依赖
    from app.engine.web.fetcher import html_to_markdown

    wrapped = f"<!DOCTYPE html><html><body>{body_html}</body></html>"
    md = html_to_markdown(wrapped, url)
    if md.strip():
        return md.strip()
    try:
        from lxml import html as lxml_html

        text = (lxml_html.fromstring(body_html).text_content() or "").strip()
    except Exception:
        text = ""
    return text
