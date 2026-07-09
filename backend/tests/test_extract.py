from app.index.extract import extract_text


def test_extract_plain_md(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("# 标题\n正文\n", encoding="utf-8")
    out = extract_text(p)
    assert "正文" in out


def test_extract_txt(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("纯文本内容", encoding="utf-8")
    assert "纯文本内容" in extract_text(p)


def test_extract_binary_returns_empty(tmp_path):
    p = tmp_path / "a.zip"
    p.write_bytes(b"PK\x03\x04binary")
    assert extract_text(p) == ""
