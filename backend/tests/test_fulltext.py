from app.index.fulltext import FullTextIndex


def test_add_and_query(tmp_path):
    fi = FullTextIndex(tmp_path / "fts.db")
    fi.add("doc1.md", ["docker 常用命令 容器"], source="doc1.md")
    fi.add("doc2.md", ["番茄炒蛋 菜谱"], source="doc2.md")
    hits = fi.query("docker", k=5)
    assert any(h.doc_id == "doc1.md" for h in hits)
    assert all(h.doc_id != "doc2.md" for h in hits)


def test_delete(tmp_path):
    fi = FullTextIndex(tmp_path / "fts.db")
    fi.add("doc1.md", ["docker"], source="doc1.md")
    fi.delete("doc1.md")
    assert fi.query("docker", k=5) == []


def test_reindex_replaces(tmp_path):
    fi = FullTextIndex(tmp_path / "fts.db")
    fi.add("doc1.md", ["旧词语"], source="doc1.md")
    fi.delete("doc1.md")
    fi.add("doc1.md", ["新词语"], source="doc1.md")
    assert fi.query("旧词语", k=5) == []
    assert any(h.doc_id == "doc1.md" for h in fi.query("新词语", k=5))


def test_query_with_markdown_special_chars(tmp_path):
    fi = FullTextIndex(tmp_path / "fts.db")
    fi.add("doc1.md", ["PowerShell 配置 `$PROFILE` 路径"], source="doc1.md")
    # 含反引号、星号等 FTS5 特殊字符时不应抛语法错误
    hits = fi.query("```powershell\n$PROFILE = `$env:USERPROFILE`", k=5)
    assert isinstance(hits, list)


def test_prepare_fts_query_ors_whitespace_keywords():
    from app.index.fulltext import prepare_fts_query

    assert prepare_fts_query("docker") == '"docker"'
    assert prepare_fts_query("向量库 本地部署") == '"向量库" OR "本地部署"'
    # 多词时优先 ≥3 码点词（trigram）；过短词不进 MATCH
    assert prepare_fts_query("合作 教培机构 本地部署") == '"教培机构" OR "本地部署"'


def test_multikeyword_chinese_query_hits(tmp_path):
    fi = FullTextIndex(tmp_path / "fts.db")
    fi.add(
        "a.md",
        ["面向教培机构的合作会谈材料，强调数据本地部署。"],
        source="运营/教培机构合作会谈材料.md",
    )
    fi.add("b.md", ["番茄炒蛋食谱"], source="b.md")
    hits = fi.query("产品介绍 教培机构 合作", k=5)
    assert any(h.source.endswith("教培机构合作会谈材料.md") for h in hits)


def test_short_chinese_query_like_fallback(tmp_path):
    fi = FullTextIndex(tmp_path / "fts.db")
    fi.add("a.md", ["数据不能出校园，合作方最关心隐私。"], source="a.md")
    hits = fi.query("合作", k=5)
    assert any(h.doc_id == "a.md" for h in hits)
