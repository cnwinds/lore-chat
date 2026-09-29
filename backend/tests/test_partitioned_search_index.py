from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass, field
from typing import Callable

import pytest

from app.index.chroma_client import make_persistent_client
from app.index.partitioned.embedder import EmbedBatch, LLMEmbedder
from app.index.partitioned.lexical import partition_family
from app.index.partitioned.search_index import (
    IndexItem,
    PartitionTuning,
    SearchIndex,
    default_gate,
)

from app.models.llm import FakeLLMClient


def _make_index(tmp_path, embedder=None, **kwargs) -> SearchIndex:
    db = tmp_path / "partitioned.db"
    vec = tmp_path / "vec"
    return SearchIndex(db, vec, embedder, **kwargs)


@dataclass
class FakeEmbedder:
    model: str = "test-model"
    dim: int = 8
    delay: float = 0.0
    error: Exception | None = None
    text_vectors: dict[str, list[float]] = field(default_factory=dict)
    on_embed: Callable[[list[str]], None] | None = None
    call_count: int = 0

    def embed(self, texts: list[str]) -> EmbedBatch:
        self.call_count += 1
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error
        if self.on_embed:
            self.on_embed(texts)
        vectors = []
        default = [0.0] + [1.0] + [0.0] * (self.dim - 2)
        for t in texts:
            vectors.append(list(self.text_vectors.get(t, default)))
        return EmbedBatch(vectors=vectors, model=self.model)


def test_invalid_partition_raises():
    with pytest.raises(ValueError):
        partition_family("kb:only-one-part")
    with pytest.raises(ValueError):
        partition_family("nocolon")
    with pytest.raises(ValueError):
        partition_family("cards:")
    with pytest.raises(ValueError):
        partition_family("cards:has space")
    with pytest.raises(ValueError):
        partition_family("cards:" + "x" * 200)


def test_search_empty_partitions_raises(tmp_path):
    idx = _make_index(tmp_path)
    with pytest.raises(ValueError):
        idx.search("q", partitions=[])


def test_sync_partition_add_update_remove(tmp_path):
    emb = FakeEmbedder()
    idx = _make_index(tmp_path, emb)
    part = "cards:role:test"

    s1 = idx.sync_partition(
        part,
        [IndexItem("a", "文本一"), IndexItem("b", "文本二")],
    )
    assert s1.added == 2 and s1.updated == 0 and s1.removed == 0

    idx.embed_pending()
    row = idx._lexical.get_item(part, "a")
    assert row["vec_state"] == "ok"

    s2 = idx.sync_partition(
        part,
        [IndexItem("a", "文本一改"), IndexItem("b", "文本二")],
    )
    assert s2.updated == 1
    row = idx._lexical.get_item(part, "a")
    assert row["vec_state"] == "pending"

    idx.embed_pending()
    assert idx._lexical.get_item(part, "a")["vec_state"] == "ok"

    s3 = idx.sync_partition(part, [IndexItem("b", "文本二")])
    assert s3.removed == 1

    s4 = idx.sync_partition(part, [IndexItem("b", "文本二")])
    assert s4.unchanged == 1
    assert idx._lexical.get_item(part, "b")["vec_state"] == "ok"


def test_drop_partition_clears_all(tmp_path):
    emb = FakeEmbedder()
    idx = _make_index(tmp_path, emb)
    part = "cards:role:drop"
    idx.sync_partition(part, [IndexItem("x", "内容")])
    idx.embed_pending()
    n = idx.drop_partition(part)
    assert n == 1
    assert idx.partitions("cards") == []
    res = idx.search("内容", partitions=[part], limit=5)
    assert not res.hits


def test_tokenizer_version_migration(tmp_path):
    idx = _make_index(tmp_path, FakeEmbedder())
    part = "cards:role:mig"
    idx.sync_partition(part, [IndexItem("1", "先查违约条款")])
    idx._lexical.force_tokenizer_version(0)
    idx2 = _make_index(tmp_path, FakeEmbedder())
    res = idx2.search("违约", partitions=[part], limit=5)
    assert res.hits


def test_partition_isolation_fts_and_vec(tmp_path):
    good = [1.0] * 8
    bad = [0.0, 1.0] + [0.0] * 6
    emb = FakeEmbedder(
        text_vectors={
            "违约": good,
            "先查违约责任条款": good,
            "无关内容": bad,
        }
    )
    idx = _make_index(tmp_path, emb)
    pa, pb = "cards:role:a", "cards:role:b"
    idx.sync_partition(pa, [IndexItem("1", "先查违约责任条款")])
    idx.sync_partition(pb, [IndexItem("2", "无关内容")])
    idx.embed_pending()

    fts = idx.search("违约", partitions=[pb], limit=5, lanes=("fts",))
    assert not fts.hits

    vec_pa = idx.search("违约", partitions=[pa], limit=5, lanes=("vec",))
    assert any(h.item_id == "1" for h in vec_pa.hits)
    assert all(h.partition == pa for h in vec_pa.hits)

    vec_pb = idx.search("违约", partitions=[pb], limit=5, lanes=("vec",))
    assert all(h.partition == pb for h in vec_pb.hits)
    assert all(h.item_id != "1" for h in vec_pb.hits)


def test_two_char_and_natural_language_query(tmp_path):
    idx = _make_index(tmp_path, FakeEmbedder())
    part = "cards:role:lex"
    text = "先查违约条款再看付款"
    idx.sync_partition(part, [IndexItem("c1", text)])

    r1 = idx.search("违约", partitions=[part], limit=5, lanes=("fts",))
    assert any(h.item_id == "c1" for h in r1.hits)

    r2 = idx.search(
        "这份合同里的违约金怎么约定",
        partitions=[part],
        limit=5,
        lanes=("fts",),
    )
    hit = next(h for h in r2.hits if h.item_id == "c1")
    assert "违约" in hit.matched_terms


def test_rare_terms_and_default_gate(tmp_path):
    idx = _make_index(tmp_path, FakeEmbedder())
    part = "cards:role:rare"
    items = [
        IndexItem(f"m{i}", f"主人相关{i}") for i in range(8)
    ]
    items.append(IndexItem("pay", "主人付款专用"))
    idx.sync_partition(part, items)

    res = idx.search(
        "主人付款",
        partitions=[part],
        limit=10,
        tunings={"cards": PartitionTuning(rare_df_ratio=0.25)},
        lanes=("fts",),
    )
    pay_hit = next(h for h in res.hits if h.item_id == "pay")
    common_hit = next(h for h in res.hits if h.item_id == "m0")
    assert "付款" in pay_hit.rare_terms
    assert "主人" not in pay_hit.rare_terms
    assert common_hit.rare_terms == ()
    pt = PartitionTuning()
    assert default_gate(pay_hit, pt)
    assert not default_gate(common_hit, pt)


def test_pure_vector_recall(tmp_path):
    target = "先查违约责任条款"
    good = [1.0] * 8
    bad = [0.0, 1.0] + [0.0] * 6
    emb = FakeEmbedder(
        text_vectors={target: good, "合同违约": good, "无关": bad}
    )
    idx = _make_index(tmp_path, emb)
    part = "cards:role:vec"
    idx.sync_partition(
        part,
        [
            IndexItem("hit", target),
            IndexItem("miss", "完全无关的说明"),
        ],
    )
    idx.embed_pending()
    res = idx.search(
        "合同违约",
        partitions=[part],
        limit=5,
        lanes=("vec",),
    )
    hit = next(h for h in res.hits if h.item_id == "hit")
    assert hit.vector_score is not None and hit.vector_score >= 0.5


def test_vector_timeout_then_cache(tmp_path):
    emb = FakeEmbedder(delay=1.0)
    idx = _make_index(tmp_path, emb)
    part = "cards:role:to"
    idx.sync_partition(part, [IndexItem("1", "超时测试内容")])
    idx.embed_pending()

    t0 = time.monotonic()
    r1 = idx.search(
        "超时测试",
        partitions=[part],
        vector_timeout_s=0.2,
    )
    assert r1.vector_status == "timeout"
    assert r1.hits
    assert r1.elapsed_ms < 600
    assert time.monotonic() - t0 < 0.6

    time.sleep(1.2)
    r2 = idx.search(
        "超时测试",
        partitions=[part],
        vector_timeout_s=0.2,
    )
    assert r2.vector_status == "ok"


def test_embed_error_and_unavailable(tmp_path):
    idx = _make_index(tmp_path, FakeEmbedder(error=RuntimeError("boom")))
    part = "cards:role:err"
    idx.sync_partition(part, [IndexItem("1", "错误降级")])
    r = idx.search("错误", partitions=[part])
    assert r.vector_status == "error"
    assert r.hits

    idx2 = _make_index(tmp_path)
    idx2.sync_partition(part, [IndexItem("1", "错误降级")])
    r2 = idx2.search("错误", partitions=[part])
    assert r2.vector_status == "unavailable"


def test_model_migration_and_mismatch(tmp_path):
    part = "cards:role:migmodel"
    idx = _make_index(tmp_path, FakeEmbedder(model="model-a"))
    idx.sync_partition(part, [IndexItem("1", "迁移文本")])
    idx.embed_pending()
    assert idx._lexical.get_meta("active_embed_model") == "model-a"
    assert idx._lexical.get_item(part, "1")["vec_model"] == "model-a"

    idx.embedder = FakeEmbedder(model="model-b")
    idx.on_embedder_changed()
    assert idx.embed_pending() == 0
    assert idx._lexical.get_meta("active_embed_model") == "model-b"
    assert idx._lexical.get_item(part, "1")["vec_model"] == "model-a"

    assert idx.embed_pending() == 1
    assert idx._lexical.get_item(part, "1")["vec_model"] == "model-b"

    client = make_persistent_client(str(tmp_path / "vec"))
    names = {c.name for c in client.list_collections()}
    a_suffix = hashlib.sha1(b"model-a").hexdigest()[:12]
    assert f"pidx_cards_{a_suffix}" not in names

    idx.embedder = FakeEmbedder(model="model-wrong")
    r = idx.search("迁移", partitions=[part])
    assert r.vector_status == "model_mismatch"
    assert r.hits


def test_same_model_rebind_no_reembed(tmp_path):
    part = "cards:role:same"
    emb = FakeEmbedder(model="model-a")
    idx = _make_index(tmp_path, emb)
    idx.sync_partition(part, [IndexItem("1", "同模型")])
    idx.embed_pending()
    emb.call_count = 0
    idx.on_embedder_changed()
    assert idx.embed_pending() == 0
    assert idx.embed_pending() == 0
    assert emb.call_count == 1
    row = idx._lexical.get_item(part, "1")
    assert row["vec_state"] == "ok"
    assert row["vec_model"] == "model-a"


def test_search_model_mismatch_triggers_probe(tmp_path):
    part = "cards:role:probe"
    idx = _make_index(tmp_path, FakeEmbedder(model="model-a"))
    idx.sync_partition(part, [IndexItem("1", "探测触发")])
    idx.embed_pending()

    idx.embedder = FakeEmbedder(model="model-b")
    r = idx.search("探测", partitions=[part])
    assert r.vector_status == "model_mismatch"

    assert idx.embed_pending() == 0
    assert idx._lexical.get_meta("active_embed_model") == "model-b"
    assert idx.embed_pending() == 1
    r2 = idx.search("探测", partitions=[part])
    assert r2.vector_status == "ok"


def test_vector_upsert_failure_not_ok(tmp_path, monkeypatch):
    emb = FakeEmbedder(model="model-a")
    idx = _make_index(tmp_path, emb)
    part = "cards:role:fail"
    idx.sync_partition(part, [IndexItem("1", "写入失败")])

    def _boom(*_args, **_kwargs):
        raise RuntimeError("upsert fail")

    monkeypatch.setattr(idx._vectors, "upsert", _boom)
    assert idx.embed_pending() == 0
    row = idx._lexical.get_item(part, "1")
    assert row["vec_state"] == "pending"
    assert row["vec_next_try_at"] > time.time()


def test_close_then_search_no_raise(tmp_path):
    idx = _make_index(tmp_path, FakeEmbedder())
    part = "cards:role:closed"
    idx.sync_partition(part, [IndexItem("1", "关闭后")])
    idx.close()
    r = idx.search("关闭", partitions=[part])
    assert r.vector_status == "unavailable"
    assert idx.embed_pending() == 0


def test_embed_pending_backoff_and_on_embedder_changed(tmp_path):
    emb = FakeEmbedder(error=RuntimeError("fail"))
    idx = _make_index(tmp_path, emb)
    part = "cards:role:backoff"
    idx.sync_partition(part, [IndexItem("1", "退避")])
    assert idx.embed_pending() == 0
    row = idx._lexical.get_item(part, "1")
    assert row["vec_attempts"] >= 1
    assert row["vec_next_try_at"] > time.time()
    assert idx.embed_pending() == 0

    idx.embedder = FakeEmbedder(model="model-a")
    idx.on_embedder_changed()
    assert idx.embed_pending() == 1


def test_embed_skips_stale_item(tmp_path):
    part = "cards:role:stale"
    idx = _make_index(tmp_path)

    def _mutate(texts):
        idx.sync_partition(part, [IndexItem("1", "嵌入期间已改")])

    emb = FakeEmbedder(model="model-a", on_embed=_mutate)
    idx.embedder = emb
    idx.sync_partition(part, [IndexItem("1", "原始文本")])
    assert idx.embed_pending() == 0
    row = idx._lexical.get_item(part, "1")
    assert row["vec_state"] == "pending"


def test_fake_llm_embed_with_model():
    llm = FakeLLMClient(embed_dim=4)
    vecs, model = llm.embed_with_model(["a"])
    assert len(vecs) == 1
    assert model == "fake-embed-4"


def test_llm_embedder_bad_return_shape():
    class Bad:
        def embed_with_model(self, texts):
            return [["a"]], 123

    with pytest.raises(TypeError):
        LLMEmbedder(Bad()).embed(["x"])
