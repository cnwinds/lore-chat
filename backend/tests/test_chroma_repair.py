import sqlite3
from pathlib import Path

from app.index import chroma_repair
from app.index.chroma_client import make_persistent_client


def _vec(seed, dim=8):
    return [float((seed + i) % 5) for i in range(dim)]


def _seed_legacy_kb(vec_path: Path, doc_id: str, chunks: list[str], embeddings, *, source: str):
    vec_path.mkdir(parents=True, exist_ok=True)
    client = make_persistent_client(str(vec_path))
    col = client.get_or_create_collection("kbs", metadata={"hnsw:space": "cosine"})
    ids = [f"{doc_id}::{i}" for i in range(len(chunks))]
    metadatas = [{"doc_id": doc_id, "source": source} for _ in chunks]
    col.add(ids=ids, documents=chunks, embeddings=embeddings, metadatas=metadatas)


def _corrupt_max_seq_id(db_path: Path) -> str:
    conn = sqlite3.connect(str(db_path))
    try:
        segment_id, _ = conn.execute(
            "SELECT segment_id, seq_id FROM max_seq_id LIMIT 1"
        ).fetchone()
        conn.execute(
            "UPDATE max_seq_id SET seq_id = 83 WHERE segment_id = ?",
            (segment_id,),
        )
        conn.commit()
        return segment_id
    finally:
        conn.close()


def test_repair_converts_integer_max_seq_id(tmp_path):
    vec_path = tmp_path / "vec"
    _seed_legacy_kb(vec_path, "doc1.md", ["docker 命令"], [_vec(1)], source="doc1.md")

    db = vec_path / "chroma.sqlite3"
    _corrupt_max_seq_id(db)

    conn = sqlite3.connect(str(db))
    try:
        types = [row[0] for row in conn.execute("SELECT typeof(seq_id) FROM max_seq_id")]
    finally:
        conn.close()
    assert "integer" in types

    fixed = chroma_repair.repair_max_seq_id_types(vec_path)
    assert fixed == 1

    conn = sqlite3.connect(str(db))
    try:
        types = [row[0] for row in conn.execute("SELECT typeof(seq_id) FROM max_seq_id")]
    finally:
        conn.close()
    assert types == ["blob"]


def test_make_persistent_client_auto_repairs_before_open(tmp_path):
    vec_path = tmp_path / "vec"
    _seed_legacy_kb(vec_path, "doc1.md", ["docker 命令"], [_vec(1)], source="doc1.md")

    db = vec_path / "chroma.sqlite3"
    _corrupt_max_seq_id(db)
    chroma_repair._repaired_paths.clear()

    make_persistent_client(str(vec_path))

    conn = sqlite3.connect(str(db))
    try:
        types = [row[0] for row in conn.execute("SELECT typeof(seq_id) FROM max_seq_id")]
    finally:
        conn.close()
    assert types == ["blob"]

    col = make_persistent_client(str(vec_path)).get_collection("kbs")
    res = col.query(query_embeddings=[_vec(1)], n_results=1)
    assert res["ids"][0]
    assert res["metadatas"][0][0]["doc_id"] == "doc1.md"
