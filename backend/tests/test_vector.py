from app.index.vector import VectorIndex


def _vec(seed, dim=8):
    return [float((seed + i) % 5) for i in range(dim)]


def test_add_and_query(tmp_path):
    vi = VectorIndex(tmp_path / "vec")
    vi.add("doc1.md", ["docker 命令", "启动容器"], [_vec(1), _vec(2)], source="doc1.md")
    vi.add("doc2.md", ["做饭菜谱"], [_vec(9)], source="doc2.md")
    hits = vi.query(_vec(1), k=1)
    assert len(hits) == 1
    assert hits[0].doc_id == "doc1.md"


def test_delete_removes_doc(tmp_path):
    vi = VectorIndex(tmp_path / "vec")
    vi.add("doc1.md", ["x"], [_vec(1)], source="doc1.md")
    vi.delete("doc1.md")
    hits = vi.query(_vec(1), k=5)
    assert all(h.doc_id != "doc1.md" for h in hits)


def test_reindex_same_doc_replaces(tmp_path):
    vi = VectorIndex(tmp_path / "vec")
    vi.add("doc1.md", ["旧内容"], [_vec(1)], source="doc1.md")
    vi.delete("doc1.md")
    vi.add("doc1.md", ["新内容"], [_vec(2)], source="doc1.md")
    hits = vi.query(_vec(2), k=5)
    texts = [h.chunk for h in hits if h.doc_id == "doc1.md"]
    assert "新内容" in texts and "旧内容" not in texts
