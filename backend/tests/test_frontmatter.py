from app.storage.frontmatter import parse, dump


def test_parse_with_frontmatter():
    text = "---\ntitle: 常用命令\ntags: [docker, cli]\n---\n正文第一行\n正文第二行\n"
    meta, body = parse(text)
    assert meta["title"] == "常用命令"
    assert meta["tags"] == ["docker", "cli"]
    assert body == "正文第一行\n正文第二行\n"


def test_parse_without_frontmatter():
    meta, body = parse("只有正文\n")
    assert meta == {}
    assert body == "只有正文\n"


def test_dump_roundtrip():
    meta = {"title": "T", "tags": ["a", "b"], "source": "chat"}
    body = "hello\nworld\n"
    text = dump(meta, body)
    meta2, body2 = parse(text)
    assert meta2["title"] == "T"
    assert meta2["tags"] == ["a", "b"]
    assert body2 == body
