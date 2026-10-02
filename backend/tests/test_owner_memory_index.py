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


def test_mark_superseded_directly_updates_owner_index(tmp_path):
    store, owner_index, _service, search = _owner_stack(tmp_path)
    store.upsert_fact(
        slot_key="preference.a",
        category="preference",
        statement="旧偏好",
        normalized_value_hash="h1",
        origin="inferred",
        status="confirmed",
        fact_id="f-old",
    )
    store.upsert_fact(
        slot_key="preference.a",
        category="preference",
        statement="新偏好",
        normalized_value_hash="h2",
        origin="inferred",
        status="confirmed",
        fact_id="f-new",
    )
    owner_index.sync()
    assert search._lexical.get_item(OWNER_PARTITION, "f-old") is not None
    store.mark_superseded("f-old", supersedes_id="f-new")
    assert search._lexical.get_item(OWNER_PARTITION, "f-old") is None


def test_coalesce_mutation_state_is_per_store_instance(tmp_path):
    calls_a: list[str] = []
    calls_b: list[str] = []
    store_a = MemoryStore(
        tmp_path / "mem_a.db",
        owner_key="a",
        on_mutated=lambda: calls_a.append("a"),
    )
    store_b = MemoryStore(
        tmp_path / "mem_b.db",
        owner_key="b",
        on_mutated=lambda: calls_b.append("b"),
    )
    store_b.upsert_fact(
        slot_key="preference.x",
        category="preference",
        statement="B 侧画像",
        normalized_value_hash="hb",
        origin="manual",
        status="confirmed",
        fact_id="fb",
    )
    calls_a.clear()
    calls_b.clear()
    with store_a._coalesce_mutations():
        store_b.mark_superseded("fb", supersedes_id=None)
    assert calls_b == ["b"]
    assert calls_a == []


def test_upsert_supersede_triggers_single_on_mutated(tmp_path):
    store, owner_index, _service, _search = _owner_stack(tmp_path)
    calls: list[int] = []

    def counting_sync() -> None:
        calls.append(1)
        owner_index.sync()

    store.on_mutated = counting_sync
    store.upsert_fact(
        slot_key="preference.topic",
        category="preference",
        statement="先给结论",
        normalized_value_hash="same-hash",
        origin="inferred",
        status="confirmed",
        fact_id="keep",
    )
    calls.clear()
    store.upsert_fact(
        slot_key="preference.other",
        category="preference",
        statement="另一句",
        normalized_value_hash="same-hash",
        origin="inferred",
        status="confirmed",
        fact_id="drop",
    )
    assert len(calls) == 1


def test_recall_falls_back_when_index_returns_empty(tmp_path):
    store, owner_index, service, _search = _owner_stack(tmp_path)
    store.upsert_fact(
        slot_key="preference.topic_fb",
        category="preference",
        statement="子串回退测试句",
        normalized_value_hash="hf",
        origin="manual",
        status="confirmed",
        fact_id="ff",
    )

    original = owner_index.search

    def empty_search(q: str, *, limit: int = 10, kind: str | None = None):
        return []

    owner_index.search = empty_search  # type: ignore[method-assign]
    try:
        out = service.recall("子串", limit=5)
    finally:
        owner_index.search = original  # type: ignore[method-assign]
    assert out["count"] == 1
    assert out["facts"][0]["fact_id"] == "ff"


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
