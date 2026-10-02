"""B1 底座扩展验收测试。"""

from __future__ import annotations

import sqlite3
import time

import pytest

from app.index.partitioned import (
    IndexItem,
    MetaFilter,
    PartitionTuning,
    SearchIndex,
)
from app.index.search_query import compile_search_query
from app.time import now_iso_seconds

from tests.test_partitioned_search_index import FakeEmbedder, _make_index


def test_compile_search_query_default_min_cjk_is_two():
    c = compile_search_query("合作 教培")
    assert "合作" in c.signal_terms
    assert "教培" in c.signal_terms


def test_sync_group_isolation_and_reconcile(tmp_path):
    emb = FakeEmbedder()
    idx = _make_index(tmp_path, emb)
    part = "kb:main"
    g1, g2 = "doc/a", "doc/b"
    idx.sync_group(
        part,
        g1,
        [
            IndexItem("a1", "组一甲"),
            IndexItem("a2", "组一乙"),
            IndexItem("a3", "组一丙"),
        ],
    )
    idx.sync_group(
        part,
        g2,
        [
            IndexItem("b1", "组二甲"),
            IndexItem("b2", "组二乙"),
            IndexItem("b3", "组二丙"),
        ],
    )
    s = idx.sync_group(
        part,
        g1,
        [IndexItem("a1", "组一甲"), IndexItem("a2", "组一乙改")],
    )
    assert s.updated == 1 and s.removed == 1
    assert len(idx.group_items(part, g1)) == 2
    assert len(idx.group_items(part, g2)) == 3


def test_drop_groups_prefix_not_c10(tmp_path):
    idx = _make_index(tmp_path, FakeEmbedder())
    part = "conv:main"
    idx.sync_group(part, "c1/a", [IndexItem("1", "会话一")])
    idx.sync_group(part, "c10/a", [IndexItem("2", "会话十")])
    n = idx.drop_groups(part, prefix="c1/")
    assert n == 1
    assert idx.groups(part) == ["c10/a"]


def test_move_group_keeps_vector(tmp_path):
    emb = FakeEmbedder()
    idx = _make_index(tmp_path, emb)
    part = "cards:role:mv"
    text = "移组保留向量"
    idx.sync_group(part, "ga", [IndexItem("x", text)])
    idx.embed_pending()
    assert idx._lexical.get_item(part, "x")["vec_state"] == "ok"
    idx.sync_group(part, "gb", [IndexItem("x", text)])
    assert idx.group_items(part, "ga") == []
    assert len(idx.group_items(part, "gb")) == 1
    row = idx._lexical.get_item(part, "x")
    assert row["vec_state"] == "ok"
    assert row["grp"] == "gb"


def test_empty_group_and_prefix_raise(tmp_path):
    idx = _make_index(tmp_path)
    part = "kb:main"
    with pytest.raises(ValueError):
        idx.sync_group(part, "", [IndexItem("1", "x")])
    with pytest.raises(ValueError):
        idx.drop_group(part, "")
    with pytest.raises(ValueError):
        idx.drop_groups(part, prefix="")


def test_legacy_schema_upgrade_without_grp(tmp_path):
    db_path = tmp_path / "legacy.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)
        """
    )
    conn.execute(
        """
        CREATE TABLE items(
          partition TEXT NOT NULL,
          item_id TEXT NOT NULL,
          family TEXT NOT NULL,
          content_hash TEXT NOT NULL,
          text TEXT NOT NULL,
          meta_json TEXT NOT NULL DEFAULT '{}',
          vec_state TEXT NOT NULL DEFAULT 'pending',
          vec_model TEXT,
          vec_attempts INTEGER NOT NULL DEFAULT 0,
          vec_next_try_at REAL NOT NULL DEFAULT 0,
          updated_at TEXT NOT NULL,
          PRIMARY KEY (partition, item_id)
        )
        """
    )
    conn.execute(
        """
        CREATE VIRTUAL TABLE fts_cards USING fts5(
          partition UNINDEXED,
          item_id UNINDEXED,
          terms,
          tokenize = 'unicode61 remove_diacritics 2'
        )
        """
    )
    now = now_iso_seconds()
    conn.execute(
        """
        INSERT INTO items(
          partition, item_id, family, content_hash, text, meta_json,
          vec_state, updated_at
        ) VALUES (?, ?, 'cards', ?, ?, '{}', 'pending', ?)
        """,
        ("cards:role:old", "c1", "abc", "旧库卡片违约条款", now),
    )
    conn.execute(
        "INSERT INTO fts_cards(partition, item_id, terms) VALUES (?, ?, ?)",
        ("cards:role:old", "c1", "违约 约条 条款 旧库 库卡 卡片"),
    )
    conn.commit()
    conn.close()

    idx = SearchIndex(db_path, tmp_path / "vec", FakeEmbedder())
    row = idx._lexical.get_item("cards:role:old", "c1")
    assert row is not None
    assert row["grp"] == ""
    res = idx.search("违约", partitions=["cards:role:old"], lanes=("fts",))
    assert any(h.item_id == "c1" for h in res.hits)


def _seed_meta_filter_corpus(idx: SearchIndex, part: str) -> None:
    idx.sync_group(
        part,
        "meta",
        [
            IndexItem(
                "s-a",
                "sharedkw alpha body",
                meta={"source": "a", "chunk_index": 0, "ok": True, "tier": 1},
            ),
            IndexItem(
                "s-b",
                "sharedkw beta body",
                meta={"source": "b", "chunk_index": 1, "ok": False, "tier": 2},
            ),
            IndexItem(
                "s-c",
                "sharedkw gamma body",
                meta={"chunk_index": 2, "ok": True, "tier": 3},
            ),
            IndexItem(
                "s-d",
                "sharedkw delta body",
                meta={"source": "a", "chunk_index": 3, "ok": False, "tier": 2},
            ),
        ],
    )


def _fts_ids(idx, part, query, **kwargs) -> set[str]:
    r = idx.search(
        query,
        partitions=[part],
        lanes=("fts",),
        fts_mode="keywords",
        tunings={"kb": PartitionTuning(fts_k=10)},
        **kwargs,
    )
    return {h.item_id for h in r.hits}


def _vec_ids(idx, part, **kwargs) -> set[str]:
    r = idx.search(
        "ignored",
        partitions=[part],
        lanes=("vec",),
        vector_text="vecq",
        tunings={"kb": PartitionTuning(vec_k=10)},
        **kwargs,
    )
    return {h.item_id for h in r.hits}


def test_meta_filter_fts_string_eq_exact_ids(tmp_path):
    idx = _make_index(tmp_path, FakeEmbedder())
    part = "kb:main"
    _seed_meta_filter_corpus(idx, part)
    assert _fts_ids(
        idx, part, "sharedkw alpha", filters=[MetaFilter("source", "eq", "a")]
    ) == {"s-a"}


def test_meta_filter_fts_string_ne_exact_ids(tmp_path):
    idx = _make_index(tmp_path, FakeEmbedder())
    part = "kb:main"
    _seed_meta_filter_corpus(idx, part)
    assert _fts_ids(
        idx, part, "sharedkw", filters=[MetaFilter("source", "ne", "a")]
    ) == {"s-b", "s-c"}


def test_meta_filter_fts_int_gte_lt_exact_ids(tmp_path):
    idx = _make_index(tmp_path, FakeEmbedder())
    part = "kb:main"
    _seed_meta_filter_corpus(idx, part)
    assert _fts_ids(
        idx,
        part,
        "sharedkw",
        filters=[
            MetaFilter("chunk_index", "gte", 1),
            MetaFilter("chunk_index", "lt", 3),
        ],
    ) == {"s-b", "s-c"}


def test_meta_filter_fts_bool_eq_exact_ids(tmp_path):
    idx = _make_index(tmp_path, FakeEmbedder())
    part = "kb:main"
    _seed_meta_filter_corpus(idx, part)
    assert _fts_ids(
        idx, part, "sharedkw", filters=[MetaFilter("ok", "eq", True)]
    ) == {"s-a", "s-c"}


def test_meta_filter_fts_combined_exact_ids(tmp_path):
    idx = _make_index(tmp_path, FakeEmbedder())
    part = "kb:main"
    _seed_meta_filter_corpus(idx, part)
    assert _fts_ids(
        idx,
        part,
        "sharedkw",
        filters=[
            MetaFilter("source", "eq", "a"),
            MetaFilter("tier", "gte", 1),
            MetaFilter("tier", "lt", 2),
        ],
    ) == {"s-a"}


def test_meta_filter_fts_strict_tier_with_filter(tmp_path):
    idx = _make_index(tmp_path, FakeEmbedder())
    part = "kb:main"
    _seed_meta_filter_corpus(idx, part)
    r = idx.search(
        "sharedkw alpha",
        partitions=[part],
        lanes=("fts",),
        fts_mode="keywords",
        filters=[MetaFilter("source", "eq", "a")],
        tunings={"kb": PartitionTuning(fts_k=10)},
    )
    assert r.fts_tiers["kb"] == "strict"
    assert {h.item_id for h in r.hits} == {"s-a"}


def test_meta_filter_fts_like_tier_with_filter(tmp_path):
    idx = _make_index(tmp_path, FakeEmbedder())
    part = "kb:main"
    idx.sync_group(
        part,
        "like",
        [
            IndexItem("L1", "zzz长词命中zzz", meta={"tag": "long"}),
            IndexItem("L2", "zzz短词zzz", meta={"tag": "short"}),
        ],
    )
    with idx._lexical._connect() as conn:
        conn.execute("DELETE FROM fts_kb")
        conn.commit()
    r = idx.search(
        "长词 短词",
        partitions=[part],
        lanes=("fts",),
        fts_mode="keywords",
        filters=[MetaFilter("tag", "eq", "long")],
    )
    assert r.fts_tiers["kb"] == "like"
    assert {h.item_id for h in r.hits} == {"L1"}


def test_meta_filter_vec_string_eq_exact_ids(tmp_path):
    vec = [1.0] + [0.0] * 7
    idx = _make_index(tmp_path, FakeEmbedder(model="m1", text_vectors={"vecq": vec}))
    part = "kb:main"
    _seed_meta_filter_corpus(idx, part)
    idx.embed_pending()
    assert _vec_ids(
        idx, part, filters=[MetaFilter("source", "eq", "a")]
    ) == {"s-a", "s-d"}


def test_meta_filter_vec_string_ne_exact_ids(tmp_path):
    vec = [1.0] + [0.0] * 7
    idx = _make_index(tmp_path, FakeEmbedder(model="m1", text_vectors={"vecq": vec}))
    part = "kb:main"
    _seed_meta_filter_corpus(idx, part)
    idx.embed_pending()
    assert _vec_ids(
        idx, part, filters=[MetaFilter("source", "ne", "a")]
    ) == {"s-b", "s-c"}


def test_meta_filter_vec_int_gte_lt_exact_ids(tmp_path):
    vec = [1.0] + [0.0] * 7
    idx = _make_index(tmp_path, FakeEmbedder(model="m1", text_vectors={"vecq": vec}))
    part = "kb:main"
    _seed_meta_filter_corpus(idx, part)
    idx.embed_pending()
    assert _vec_ids(
        idx,
        part,
        filters=[
            MetaFilter("chunk_index", "gte", 1),
            MetaFilter("chunk_index", "lt", 3),
        ],
    ) == {"s-b", "s-c"}


def test_meta_filter_vec_bool_eq_exact_ids(tmp_path):
    vec = [1.0] + [0.0] * 7
    idx = _make_index(tmp_path, FakeEmbedder(model="m1", text_vectors={"vecq": vec}))
    part = "kb:main"
    _seed_meta_filter_corpus(idx, part)
    idx.embed_pending()
    assert _vec_ids(
        idx, part, filters=[MetaFilter("ok", "eq", True)]
    ) == {"s-a", "s-c"}


def test_meta_filter_vec_combined_exact_ids(tmp_path):
    vec = [1.0] + [0.0] * 7
    idx = _make_index(tmp_path, FakeEmbedder(model="m1", text_vectors={"vecq": vec}))
    part = "kb:main"
    _seed_meta_filter_corpus(idx, part)
    idx.embed_pending()
    assert _vec_ids(
        idx,
        part,
        filters=[
            MetaFilter("source", "eq", "a"),
            MetaFilter("tier", "gte", 1),
            MetaFilter("tier", "lt", 2),
        ],
    ) == {"s-a"}


def test_meta_value_passes_incomparable_types(tmp_path):
    from app.index.partitioned.search_index import _meta_value_passes

    assert not _meta_value_passes({"n": "1"}, MetaFilter("n", "gte", 2))
    assert not _meta_value_passes({"n": "1"}, MetaFilter("n", "lt", 2))


def test_meta_filter_invalid_raises():
    with pytest.raises(ValueError):
        MetaFilter("bad-key", "eq", "x")
    with pytest.raises(ValueError):
        MetaFilter("source", "badop", "x")
    with pytest.raises(ValueError):
        MetaFilter("source", "in", ())
    with pytest.raises(ValueError):
        MetaFilter("source", "in", ["a"] * 1001)


def test_meta_filter_in_fts_and_vec(tmp_path):
    idx = _make_index(tmp_path, FakeEmbedder(text_vectors={"vecq": [1.0] * 8}))
    part = "kb:main"
    _seed_meta_filter_corpus(idx, part)
    idx.embed_pending()
    assert _fts_ids(
        idx,
        part,
        "sharedkw",
        filters=[MetaFilter("source", "in", ("a", "b"))],
    ) == {"s-a", "s-b", "s-d"}
    assert _vec_ids(
        idx,
        part,
        filters=[MetaFilter("source", "in", ("a",))],
    ) == {"s-a", "s-d"}


def test_group_prefix_filter_fts_and_vec(tmp_path):
    good = [1.0] * 8
    emb = FakeEmbedder(text_vectors={"prefixq": good})
    idx = _make_index(tmp_path, emb)
    part = "kb:main"
    idx.sync_group(part, "docs/a.md", [IndexItem("a", "prefixkw alpha")])
    idx.sync_group(part, "docs/sub/b.md", [IndexItem("b", "prefixkw beta")])
    idx.sync_group(part, "other/c.md", [IndexItem("c", "prefixkw gamma")])
    idx.embed_pending()
    fts = idx.search(
        "prefixkw",
        partitions=[part],
        lanes=("fts",),
        group_prefixes=["docs/"],
    )
    assert {h.item_id for h in fts.hits} == {"a", "b"}
    vec = idx.search(
        "prefixq",
        partitions=[part],
        lanes=("vec",),
        group_prefixes=["docs/sub/"],
    )
    assert {h.item_id for h in vec.hits} == {"b"}


def test_group_prefix_empty_raises(tmp_path):
    idx = _make_index(tmp_path, FakeEmbedder())
    with pytest.raises(ValueError):
        idx.search("q", partitions=["kb:main"], group_prefixes=[""])


def test_vec_filter_without_chroma_meta(tmp_path):
    """Chroma 缺 meta 时靠回表过滤。"""
    good = [1.0] * 8
    emb = FakeEmbedder(text_vectors={"q": good})
    idx = _make_index(tmp_path, emb)
    part = "kb:main"
    idx.sync_group(
        part,
        "d1",
        [
            IndexItem("1", "only a", meta={"source": "a"}),
            IndexItem("2", "only b", meta={"source": "b"}),
        ],
    )
    idx.embed_pending()
    model = idx._lexical.get_meta("active_embed_model")
    idx._vectors.upsert(
        "kb",
        model,
        [
            (part, "1", "only a", good, {}),
            (part, "2", "only b", good, {}),
        ],
    )
    r = idx.search(
        "only",
        partitions=[part],
        lanes=("vec",),
        vector_text="q",
        filters=[MetaFilter("source", "eq", "a")],
    )
    assert any(h.item_id == "1" for h in r.hits)
    assert all(h.meta.get("source") == "a" for h in r.hits)


def test_keywords_two_char_strict(tmp_path):
    idx = _make_index(tmp_path, FakeEmbedder())
    part = "kb:main"
    idx.sync_group(part, "doc", [IndexItem("1", "分区检索底座扩展")])
    res = idx.search(
        "分区",
        partitions=[part],
        fts_mode="keywords",
        lanes=("fts",),
    )
    assert res.fts_tiers["kb"] == "strict"
    assert "kb:fts" in res.lanes


def test_keywords_strict_vs_relaxed(tmp_path):
    idx = _make_index(tmp_path, FakeEmbedder())
    part = "kb:main"
    idx.sync_group(
        part,
        "doc",
        [IndexItem("1", "分区检索"), IndexItem("2", "只有分区")],
    )
    both = idx.search(
        "分区 检索",
        partitions=[part],
        fts_mode="keywords",
        lanes=("fts",),
    )
    assert both.fts_tiers["kb"] == "strict"

    one = idx.search(
        "分区 缺失词",
        partitions=[part],
        fts_mode="keywords",
        lanes=("fts",),
    )
    assert one.fts_tiers["kb"] == "relaxed"


def test_keywords_like_tier_bm25_zero(tmp_path):
    idx = _make_index(tmp_path, FakeEmbedder())
    part = "kb:main"
    idx.sync_group(part, "doc", [IndexItem("1", "xxx特殊子串yyy")])
    with idx._lexical._connect() as conn:
        conn.execute("DELETE FROM fts_kb WHERE item_id=?", ("1",))
        conn.commit()
    res = idx.search(
        "特殊子串",
        partitions=[part],
        fts_mode="keywords",
        lanes=("fts",),
    )
    assert res.fts_tiers["kb"] == "like"
    hit = res.lanes["kb:fts"][0]
    assert hit.bm25 == 0.0


def test_keywords_skip_strict_when_five_terms(tmp_path):
    idx = _make_index(tmp_path, FakeEmbedder())
    part = "kb:main"
    idx.sync_group(part, "doc", [IndexItem("1", "一 二 三 四 五 六")])
    res = idx.search(
        "一 二 三 四 五",
        partitions=[part],
        fts_mode="keywords",
        lanes=("fts",),
    )
    assert res.fts_tiers["kb"] in ("relaxed", "like", "none")
    assert res.fts_tiers["kb"] != "strict"


def test_query_embed_cache_sync_put_no_double_embed(tmp_path):
    emb = FakeEmbedder(delay=0.05)
    idx = _make_index(tmp_path, emb)
    part = "kb:main"
    idx.sync_group(part, "d", [IndexItem("1", "内容")])
    idx.embed_pending()
    for _ in range(20):
        idx._query_cache.clear()
        emb.call_count = 0
        idx.search(
            "query-a",
            partitions=[part],
            lanes=("vec",),
            vector_text="cache-sync-text",
        )
        idx.search(
            "query-b",
            partitions=[part],
            lanes=("vec",),
            vector_text="cache-sync-text",
        )
        assert emb.call_count == 1


def test_keywords_strict_uses_phrase_count_not_signal_count(tmp_path):
    idx = _make_index(tmp_path, FakeEmbedder())
    part = "kb:main"
    idx.sync_group(part, "doc", [IndexItem("1", "词一 词二 词三 词四 正文")])
    compiled = compile_search_query("词一 词二 词三 词四 ……")
    assert len(compiled.signal_terms) >= 5
    r = idx.search(
        "词一 词二 词三 词四 ……",
        partitions=[part],
        fts_mode="keywords",
        lanes=("fts",),
    )
    assert r.fts_tiers["kb"] == "strict"
    assert {h.item_id for h in r.hits} == {"1"}


def test_keywords_like_prefers_longer_like_term(tmp_path):
    idx = _make_index(tmp_path, FakeEmbedder())
    part = "kb:main"
    idx.sync_group(
        part,
        "doc",
        [
            IndexItem("short", "body短词x", meta={"which": "short"}),
            IndexItem("long", "body长词子串x", meta={"which": "long"}),
        ],
    )
    with idx._lexical._connect() as conn:
        conn.execute("DELETE FROM fts_kb")
        conn.commit()
    r = idx.search(
        "短词 长词子串",
        partitions=[part],
        fts_mode="keywords",
        lanes=("fts",),
    )
    assert r.fts_tiers["kb"] == "like"
    assert r.lanes["kb:fts"][0].item_id == "long"


def test_vector_text_and_embed_cache(tmp_path):
    emb = FakeEmbedder()
    idx = _make_index(tmp_path, emb)
    part = "kb:main"
    idx.sync_group(part, "d", [IndexItem("1", "内容")])
    idx.embed_pending()
    emb.call_count = 0
    idx.search(
        "无关 query",
        partitions=[part],
        vector_text="嵌入专用",
        lanes=("vec",),
    )
    assert emb.call_count == 1
    idx.search(
        "另一 query",
        partitions=[part],
        vector_text="嵌入专用",
        lanes=("vec",),
    )
    assert emb.call_count == 1


def test_adopt_vectors(tmp_path):
    emb = FakeEmbedder()
    idx = _make_index(tmp_path, emb)
    part = "kb:main"
    text = "沿用文本"
    idx.sync_group(part, "g", [IndexItem("1", text)])
    vec = [0.5] * 8
    n = idx.adopt_vectors(part, [("1", text, vec)], model="legacy-m")
    assert n == 1
    row = idx._lexical.get_item(part, "1")
    assert row["vec_state"] == "ok"
    assert row["vec_model"] == "legacy-m"
    assert emb.call_count == 0

    idx.sync_group(part, "g", [IndexItem("1", text + "改")])
    assert idx._lexical.get_item(part, "1")["vec_state"] == "pending"
    n2 = idx.adopt_vectors(part, [("1", text, vec)], model="legacy-m")
    assert n2 == 0

    idx._lexical.set_meta("active_embed_model", "other")
    assert idx.adopt_vectors(part, [("1", text, vec)], model="legacy-m") == 0


def test_adopt_vectors_meta_filter(tmp_path):
    vec = [1.0] + [0.0] * 7
    idx = _make_index(tmp_path, FakeEmbedder(model="m1", text_vectors={"t": vec}))
    part = "kb:main"
    idx.sync_group(
        part,
        "g",
        [IndexItem("1", "t", meta={"source": "doc-a"})],
    )
    idx.adopt_vectors(part, [("1", "t", vec)], model="m1")
    r = idx.search(
        "t",
        partitions=[part],
        lanes=("vec",),
        vector_text="t",
        filters=[MetaFilter("source", "eq", "doc-a")],
    )
    assert any(h.item_id == "1" for h in r.hits)


def test_embedding_held_skips_family(tmp_path):
    cards_part = "cards:role:h"
    kb_part = "kb:main"
    emb = FakeEmbedder()
    idx = _make_index(tmp_path, emb)
    idx.sync_partition(cards_part, [IndexItem("c", "卡片")])
    idx.sync_group(kb_part, "d", [IndexItem("k", "文档")])
    with idx.embedding_held("kb"):
        assert idx.embed_pending(limit=10) == 1
        row = idx._lexical.get_item(kb_part, "k")
        assert row["vec_state"] == "pending"
    assert idx.embed_pending(limit=10) >= 1


def test_embed_pending_newest_first(tmp_path):
    emb = FakeEmbedder()
    idx = _make_index(tmp_path, emb)
    part = "kb:main"
    idx.sync_group(part, "a", [IndexItem("old", "旧")])
    time.sleep(1.1)
    idx.sync_group(part, "b", [IndexItem("new", "新")])
    emb.on_embed = lambda texts: None
    idx.embed_pending(limit=1)
    row = idx._lexical.get_item(part, "new")
    assert row["vec_state"] == "ok"
    assert idx._lexical.get_item(part, "old")["vec_state"] == "pending"


def test_validate_meta_rejects_reserved(tmp_path):
    idx = _make_index(tmp_path)
    with pytest.raises(ValueError):
        idx._normalize_items([IndexItem("1", "t", meta={"partition": "x"})])


def test_compile_min_cjk_signal_two():
    c = compile_search_query("分区 检索", min_cjk_signal=2)
    assert "分区" in c.signal_terms
    assert "检索" in c.signal_terms


def test_probe_model(tmp_path):
    idx = _make_index(tmp_path, FakeEmbedder(model="probe-m"))
    assert idx.probe_model() == "probe-m"
    idx2 = _make_index(tmp_path / "2", FakeEmbedder(model="unknown"))
    assert idx2.probe_model() is None
