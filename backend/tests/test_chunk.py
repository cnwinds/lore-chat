from app.index.chunk import chunk_text


def test_chunk_short_text_single_chunk():
    chunks = chunk_text("hello world", size=100, overlap=10)
    assert chunks == ["hello world"]


def test_chunk_long_text_overlaps():
    text = "a" * 250
    chunks = chunk_text(text, size=100, overlap=20)
    assert len(chunks) == 3
    assert all(len(c) <= 100 for c in chunks)
    # 相邻块有重叠
    assert chunks[0][-20:] == chunks[1][:20]


def test_chunk_empty_returns_empty():
    assert chunk_text("   ", size=100, overlap=10) == []
