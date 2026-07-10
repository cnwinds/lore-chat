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
