from __future__ import annotations

from app.engine.memory.owner_index import OWNER_PARTITION, OwnerMemoryIndex
from app.engine.memory.service import MemoryService
from app.engine.memory.store import MemoryStore
from app.index.partitioned import MetaFilter, SearchIndex
from app.storage.repo import KnowledgeRepo
from tests.helpers import make_writer
from tests.test_card_index import FakeEmbedder


def _owner_stack(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    writer = make_writer(repo, tmp_path)
    store = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    idx_dir = tmp_path / "idx"
    search = SearchIndex(
        idx_dir / "partitioned.db",
        idx_dir / "vec",
        FakeEmbedder(),
    )
    owner_index = OwnerMemoryIndex(search, store)
    store.on_mutated = owner_index.sync
    service = MemoryService(
        store,
        repo,
        knowledge_writer=writer,
        owner_index=owner_index,
    )
    return store, owner_index, service, search


def test_sync_on_mutation(tmp_path):
    store, owner_index, _service, search = _owner_stack(tmp_path)
    store.upsert_fact(
        slot_key="preference.topic_abc",
        category="preference",
        statement="主人偏好先给结论",
        normalized_value_hash="h1",
        origin="explicit_remember",
        status="confirmed",
        fact_id="f1",
    )
    assert search._lexical.get_item(OWNER_PARTITION, "f1") is not None


def test_recall_回源_drops_forgotten(tmp_path):
    store, owner_index, service, search = _owner_stack(tmp_path)
    store.upsert_fact(
        slot_key="preference.topic_a",
        category="preference",
        statement="周末整块学习",
        normalized_value_hash="h1",
        origin="explicit_remember",
        status="confirmed",
        fact_id="f1",
    )
    owner_index.sync()
    store.mark_forgotten("f1")
    out = service.recall("周末", limit=5)
    assert out["count"] == 0
    assert search._lexical.get_item(OWNER_PARTITION, "f1") is None


def test_kind_filter(tmp_path):
    store, owner_index, _, search = _owner_stack(tmp_path)
    store.upsert_fact(
        slot_key="identity.topic_a",
        category="identity",
        statement="长期做教育科技产品",
        normalized_value_hash="h1",
        origin="inferred",
        status="confirmed",
        fact_id="f1",
    )
    store.upsert_fact(
        slot_key="preference.topic_b",
        category="preference",
        statement="教育科技方向偏好",
        normalized_value_hash="h2",
        origin="inferred",
        status="confirmed",
        fact_id="f2",
    )
    owner_index.sync()
    hits = owner_index.search("教育科技", limit=10, kind="identity")
    assert len(hits) == 1
    assert hits[0]["id"] == "f1"
    res = search.search(
        "教育科技",
        partitions=[OWNER_PARTITION],
        filters=[MetaFilter("kind", "eq", "preference")],
        limit=10,
    )
    assert {h.item_id for h in res.hits} <= {"f2"}


def test_recall_fallback_without_index(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    writer = make_writer(repo, tmp_path)
    store = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    service = MemoryService(store, repo, knowledge_writer=writer, owner_index=None)
    store.upsert_fact(
        slot_key="preference.topic_x",
        category="preference",
        statement="子串匹配测试句",
        normalized_value_hash="hx",
        origin="manual",
        status="confirmed",
        fact_id="fx",
    )
    out = service.recall("子串", limit=5)
    assert out["count"] == 1
    assert out["facts"][0]["fact_id"] == "fx"
