from app.engine.disclosure import (
    DEEP_DISCLOSURE_CHARS,
    MAX_DISCLOSURE_CHARS,
    build_outline,
    disclose,
    disclosure_summary,
    resolve_disclosure_limit,
)


def test_disclose_first_window_has_more():
    text = "a" * 8000
    info = disclose(text, offset=0, limit=3000)
    assert info["total_chars"] == 8000
    assert info["offset"] == 0
    assert info["returned_chars"] == 3000
    assert info["has_more"] is True
    assert info["next_offset"] == 3000
    assert info["body"] == "a" * 3000


def test_disclose_continue_to_end():
    text = "a" * 8000
    info = disclose(text, offset=6000, limit=3000)
    assert info["returned_chars"] == 2000
    assert info["has_more"] is False
    assert "next_offset" not in info


def test_disclose_offset_clamped():
    text = "abc"
    info = disclose(text, offset=999, limit=3000)
    assert info["offset"] == 3
    assert info["returned_chars"] == 0
    assert info["has_more"] is False


def test_build_outline_positions():
    text = "# 标题A\n正文\n## 小节1\n更多\n### 深一层\n结尾"
    outline = build_outline(text)
    assert outline[0].startswith("# 标题A @0")
    assert any(o.startswith("## 小节1 @") for o in outline)
    assert any(o.startswith("### 深一层 @") for o in outline)


def test_disclose_with_outline_only_when_requested():
    text = "# 标题\n" + "x" * 5000
    assert "outline" in disclose(text, with_outline=True)
    assert "outline" not in disclose(text, with_outline=False)


def test_disclosure_summary_wording():
    info = disclose("a" * 8000, offset=0, limit=3000)
    msg = disclosure_summary("读取 x.md", info)
    assert "3000" in msg
    assert "offset=3000" in msg


def test_resolve_disclosure_limit_by_intent():
    assert resolve_disclosure_limit() == 3000
    assert resolve_disclosure_limit(intent="spot") == 3000
    assert resolve_disclosure_limit(intent="deep") == DEEP_DISCLOSURE_CHARS
    assert resolve_disclosure_limit(intent="deep", limit=12000) == 12000
    assert resolve_disclosure_limit(limit=999999) == MAX_DISCLOSURE_CHARS
    assert resolve_disclosure_limit(intent="nope") == 3000


def test_disclose_hard_caps_limit():
    text = "a" * 50_000
    info = disclose(text, offset=0, limit=999999)
    assert info["returned_chars"] == MAX_DISCLOSURE_CHARS
    assert info["has_more"] is True
