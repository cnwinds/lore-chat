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
