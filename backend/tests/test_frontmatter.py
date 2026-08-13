from app.storage.frontmatter import parse, dump


def test_parse_legacy_frontmatter():
    text = "---\ntitle: 常用命令\ntags: [docker, cli]\n---\n正文第一行\n正文第二行\n"
    meta, body = parse(text)
    assert meta["title"] == "常用命令"
    assert meta["tags"] == ["docker", "cli"]
    assert body == "正文第一行\n正文第二行\n"


def test_parse_without_frontmatter():
    meta, body = parse("只有正文\n")
    assert meta == {}
    assert body == "只有正文\n"


def test_dump_uses_lore_meta_delim():
    meta = {"title": "T", "tags": ["a", "b"], "source": "chat"}
    body = "hello\nworld\n"
    text = dump(meta, body)
    assert text.startswith("<<<LORE_META\n")
    assert "LORE_META>>>\n" in text
    assert not text.startswith("---\n")
    meta2, body2 = parse(text)
    assert meta2["title"] == "T"
    assert meta2["tags"] == ["a", "b"]
    assert body2 == body


def test_skill_yaml_body_not_parsed_as_meta_with_lore_header():
    """KB 头用 LORE_META 后，正文内 --- Skill YAML 不会进 meta。"""
    body = "---\nname: demo\ndescription: x\n---\n\n# Demo\n\nbody\n"
    text = dump({"title": "demo", "source": "chat"}, body)
    meta, parsed_body = parse(text)
    assert meta.get("title") == "demo"
    assert "name" not in meta
    assert "description" not in meta
    assert parsed_body.startswith("---\nname: demo")


def test_legacy_then_rewrite_migrates_delim(tmp_path):
    from app.storage.repo import KnowledgeRepo

    repo = KnowledgeRepo(tmp_path)
    legacy = "---\ntitle: Old\ntags: [a]\n---\nbody line\n"
    (tmp_path / "x.md").write_text(legacy, encoding="utf-8")
    # bypass write_doc to plant legacy file without commit complexity
    abs_p = repo.abs_path("x.md")
    abs_p.write_text(legacy, encoding="utf-8")
    doc = repo.read_doc("x.md")
    assert doc.meta["title"] == "Old"
    assert doc.body == "body line\n"
    repo.write_doc("x.md", doc.meta, doc.body, commit_msg="migrate")
    raw = abs_p.read_text(encoding="utf-8")
    assert raw.startswith("<<<LORE_META\n")
    assert "---\ntitle:" not in raw
