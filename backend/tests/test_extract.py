from pathlib import Path

from app.index.extract import extract_text, extract_text_from_bytes


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


def test_extract_text_from_bytes_pdf():
    data = (Path(__file__).parent / "fixtures" / "dummy.pdf").read_bytes()
    out = extract_text_from_bytes(data, file_extension=".pdf")
    assert out.error is None
    assert "Dummy PDF" in out.text


def test_extract_text_from_bytes_unsupported_type():
    out = extract_text_from_bytes(b"PK\x03\x04", file_extension=".zip")
    assert out.text == ""
    assert out.error is not None
    assert "不支持" in out.error
