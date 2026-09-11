from app.index.search_query import compile_search_query, prepare_fts_query


def test_latin_phrase_merged():
    c = compile_search_query("Media Grant 不透明 capability URL")
    assert "Media Grant" in c.signal_terms
    assert "不透明" in c.signal_terms
    assert "capability" in c.signal_terms
    assert "URL" not in c.signal_terms
    assert "url" not in [t.lower() for t in c.signal_terms]


def test_strict_and_for_few_terms():
    c = compile_search_query("Media Grant 不透明 capability")
    assert c.strict_fts is not None
    assert " AND " in c.strict_fts
    assert '"Media Grant"' in c.strict_fts


def test_relaxed_or_for_multiple_terms():
    c = compile_search_query("向量库 本地部署")
    assert c.relaxed_fts == '"向量库" OR "本地部署"'


def test_short_chinese_fallback_to_all_terms():
    c = compile_search_query("合作 教培机构 本地部署")
    assert "教培机构" in c.signal_terms
    assert "本地部署" in c.signal_terms
    assert prepare_fts_query("合作 教培机构 本地部署") == '"教培机构" OR "本地部署"'


def test_low_signal_latin_dropped_when_alone():
    c = compile_search_query("docker url http")
    assert "docker" in c.signal_terms
    assert "url" not in [t.lower() for t in c.signal_terms]


def test_vector_text_uses_signal_terms():
    c = compile_search_query("Media Grant 不透明")
    assert c.vector_text == "Media Grant 不透明"


def test_latin_keyword_query_splits_for_and_or():
    """整句英文关键词不能当成必现邻接短语，否则 grok slack 会搜空。"""
    c = compile_search_query("grok slack")
    assert c.signal_terms == ("grok", "slack")
    assert c.match_terms == ("grok", "slack")
    assert c.like_terms == ("grok", "slack")
    assert c.strict_fts == '"grok" AND "slack"'
    assert c.relaxed_fts == '"grok" OR "slack"'
    assert c.vector_text == "grok slack"


def test_mixed_query_keeps_latin_phrase_atomic():
    c = compile_search_query("Media Grant 不透明")
    assert c.signal_terms == ("Media Grant", "不透明")
    assert '"Media Grant"' in (c.strict_fts or "")
