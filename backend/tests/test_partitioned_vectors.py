from __future__ import annotations

import numpy as np
import pytest

from app.index.partitioned import IndexItem, MetaFilter, PartitionTuning, SearchIndex
from app.index.partitioned import vectors
from app.index.partitioned.vectors import remove_legacy_vector_dir
from tests.test_partitioned_search_index import FakeEmbedder, _make_index


def _vector_rows(idx) -> dict[tuple[str, str], str]:
    with idx._lexical._connect() as conn:
        return {
            (r["partition"], r["item_id"]): r["model"]
            for r in conn.execute("SELECT partition, item_id, model FROM vectors")
        }


def test_encode_normalizes_and_keeps_zero():
    raw = np.frombuffer(vectors.encode([3.0, 4.0]), dtype="<f4")
    assert np.allclose(raw, [0.6, 0.8])
    assert np.frombuffer(vectors.encode([0.0, 0.0]), dtype="<f4").tolist() == [0.0, 0.0]
    with pytest.raises(ValueError):
        vectors.encode([])
    with pytest.raises(ValueError):
        vectors.encode([float("nan"), 1.0])


def test_top_k_orders_by_cosine_across_batches_and_skips_wrong_dim():
    rows = [
        ("p", "far", vectors.encode([0.0, 1.0])),
        ("p", "near", vectors.encode([1.0, 0.1])),
        ("p", "mid", vectors.encode([1.0, 1.0])),
        ("p", "olddim", vectors.encode([1.0, 0.0, 0.0])),
    ]
    hits = vectors.top_k([rows[:2], rows[2:]], [1.0, 0.0], 2)
    assert [h[1] for h in hits] == ["near", "mid"]
    assert hits[0][2] == pytest.approx(1 / np.sqrt(1.01), rel=1e-5)
    assert vectors.top_k([rows], [1.0, 0.0], 0) == []


def test_vectors_follow_item_lifecycle(tmp_path):
    idx = _make_index(tmp_path, FakeEmbedder())
    part = "kb:main"
    idx.sync_group(part, "d", [IndexItem("1", "一"), IndexItem("2", "二")])
    idx.embed_pending()
    assert set(_vector_rows(idx)) == {(part, "1"), (part, "2")}

    idx.sync_group(part, "d", [IndexItem("1", "一改"), IndexItem("2", "二")])
    assert set(_vector_rows(idx)) == {(part, "2")}
    assert idx._lexical.get_item(part, "1")["vec_state"] == "pending"

    idx.delete(part, ["2"])
    assert _vector_rows(idx) == {}
    idx.embed_pending()
    idx.drop_group(part, "d")
    assert _vector_rows(idx) == {}


def test_ok_items_without_vector_rows_return_to_pending(tmp_path):
    idx = _make_index(tmp_path, FakeEmbedder(model="m"))
    part = "cards:role:legacy"
    idx.sync_partition(part, [IndexItem("1", "曾在 Chroma")])
    idx.embed_pending()
    with idx._lexical._connect() as conn:
        conn.execute("DELETE FROM vectors")
    idx.close()

    reopened = SearchIndex(tmp_path / "partitioned.db", FakeEmbedder(model="m"))
    row = reopened._lexical.get_item(part, "1")
    assert row["vec_state"] == "pending"
    assert row["vec_model"] is None
    assert reopened.embed_pending() == 1
    assert _vector_rows(reopened) == {(part, "1"): "m"}


def test_only_active_model_vectors_are_queried(tmp_path):
    good = [1.0] + [0.0] * 7
    idx = _make_index(tmp_path, FakeEmbedder(model="a", text_vectors={"q": good, "x": good}))
    part = "cards:role:mix"
    idx.sync_partition(part, [IndexItem("1", "x")])
    idx.embed_pending()
    idx.embedder = FakeEmbedder(model="b", text_vectors={"q": good})
    idx.on_embedder_changed()
    idx.embed_pending()
    assert idx._lexical.get_meta("active_embed_model") == "b"
    with idx._lexical._connect() as conn:
        conn.execute("UPDATE items SET vec_next_try_at=1e18")
    r = idx.search("q", partitions=[part], lanes=("vec",), vector_text="q")
    assert r.vector_status == "ok"
    assert r.hits == []


def test_range_filter_and_group_prefix_applied_before_top_k(tmp_path):
    good = [1.0] * 8
    idx = _make_index(tmp_path, FakeEmbedder(text_vectors={"q": good}))
    part = "conv:main"
    for i in range(30):
        idx.sync_group(part, f"c1/m{i}", [IndexItem(f"old{i}", f"旧 {i}", meta={"ts": "2026-01-01"})])
    idx.sync_group(part, "c2/m0", [IndexItem("new", "新", meta={"ts": "2026-10-01"})])
    while idx.embed_pending(limit=64):
        pass
    r = idx.search(
        "q",
        partitions=[part],
        lanes=("vec",),
        vector_text="q",
        filters=[MetaFilter("ts", "gte", "2026-06-01")],
        group_prefixes=["c2/"],
        tunings={"conv": PartitionTuning(vec_k=3)},
    )
    assert [h.item_id for h in r.hits] == ["new"]


def test_in_and_ne_filters_on_vector_lane(tmp_path):
    good = [1.0] * 8
    idx = _make_index(tmp_path, FakeEmbedder(text_vectors={"q": good}))
    part = "conv:main"
    idx.sync_group(
        part,
        "g",
        [IndexItem(f"i{n}", f"t{n}", meta={"conversation_id": f"c{n}"}) for n in range(4)],
    )
    idx.embed_pending()
    r = idx.search(
        "q",
        partitions=[part],
        lanes=("vec",),
        vector_text="q",
        filters=[
            MetaFilter("conversation_id", "in", ("c1", "c2", "c3")),
            MetaFilter("conversation_id", "ne", "c2"),
        ],
    )
    assert {h.item_id for h in r.hits} == {"i1", "i3"}


def test_remove_legacy_vector_dir(tmp_path):
    vec = tmp_path / "vec"
    (vec / "abc").mkdir(parents=True)
    (vec / "chroma.sqlite3").write_bytes(b"x")
    remove_legacy_vector_dir(tmp_path)
    assert not vec.exists()
    remove_legacy_vector_dir(tmp_path)
