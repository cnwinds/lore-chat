from app.storage.frontmatter import parse, dump


def test_leading_yaml_stays_in_body_not_kb_meta():
    """正文 --- 不再当作 KB meta（与 Skill 触发头共存）。"""
    text = "---\ntitle: 常用命令\ntags: [docker, cli]\n---\n正文第一行\n正文第二行\n"
    meta, body = parse(text)
    assert meta == {}
    assert body == text


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


def test_import_skill_md_preserves_trigger_yaml(tmp_path):
    from app.storage.repo import KnowledgeRepo
    from tests.helpers import make_writer

    repo = KnowledgeRepo(tmp_path)
    writer = make_writer(repo, tmp_path)
    raw = "---\nname: demo\ndescription: Use when demo.\n---\n\n# Demo\n"
    out = writer.import_entry(
        directory="技能/demo", filename="SKILL.md", data=raw.encode()
    )
    assert out["rel_path"] == "技能/demo/SKILL.md"
    doc = repo.read_doc(out["rel_path"])
    assert "name: demo" in doc.body
    assert "description: Use when demo." in doc.body
    assert "name" not in doc.meta
