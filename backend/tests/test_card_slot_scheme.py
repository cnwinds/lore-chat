from app.engine.memory.constants import ORIGIN_RANK
from app.engine.memory.normalize import (
    CARD_SCHEME,
    OWNER_SCHEME,
    canonicalize_slot_key,
    normalize_slot_key,
    resolve_slot_key,
)
from app.engine.memory.policy import initial_status, should_promote
from app.engine.memory.resolver import SlotAction, SlotResolver
from app.engine.memory.store import MemoryStore
from tests.helpers import make_writer
from app.storage.repo import KnowledgeRepo


def test_owner_scheme_canonicalize_unchanged():
    assert canonicalize_slot_key("reading_habit", scheme=OWNER_SCHEME) is None
    assert canonicalize_slot_key("identity.name", scheme=OWNER_SCHEME) == "identity.name"
    assert canonicalize_slot_key("lesson.audio_limit", scheme=OWNER_SCHEME) is None
    slot = resolve_slot_key(
        "workflow",
        "我习惯每天早上读书一小时",
        slot_hint="reading_habit",
        scheme=OWNER_SCHEME,
    )
    assert slot.startswith("workflow.")
    assert "reading_habit" not in slot
    assert "preference" not in slot


def test_card_scheme_slot_keys():
    assert canonicalize_slot_key("lesson.audio_limit", scheme=CARD_SCHEME) == (
        "lesson.audio_limit"
    )
    assert canonicalize_slot_key("identity.name", scheme=CARD_SCHEME) == "domain.name"
    assert canonicalize_slot_key("audio_limit", scheme=CARD_SCHEME) == "domain.audio_limit"
    slot = resolve_slot_key(
        "domain",
        "某领域规则",
        slot_hint="preference.illustration_style",
        scheme=CARD_SCHEME,
    )
    assert slot.startswith("domain.")
    assert "preference" not in slot


def test_card_scheme_allows_sensitive_autowrite(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    make_writer(repo, tmp_path)
    store = MemoryStore(tmp_path / "memory.db", owner_key="role:r1")
    resolver = SlotResolver(store, scheme=CARD_SCHEME)
    stmt = "本领域涉及银行对公流程的常见材料清单"
    out = resolver.apply(
        SlotAction(
            action="new",
            statement=stmt,
            category="domain",
            origin="direct",
            confidence=0.9,
            slot_hint="domain.bank_docs",
        ),
        conversation_id="c1",
    )
    assert out.get("ok") is True
    assert out["fact"]["status"] == "confirmed"


def test_owner_scheme_still_blocks_sensitive(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    make_writer(repo, tmp_path)
    store = MemoryStore(tmp_path / "memory.db", owner_key="owner")
    resolver = SlotResolver(store, scheme=OWNER_SCHEME)
    out = resolver.apply(
        SlotAction(
            action="new",
            statement="我的银行账户在上海某支行",
            category="preference",
            origin="direct",
            confidence=0.9,
            slot_hint="preference.bank",
        ),
        conversation_id="c1",
    )
    assert out.get("ok") is False
    assert out.get("error") == "rejected"


def test_external_origin_policy(tmp_path):
    store = MemoryStore(tmp_path / "memory.db", owner_key="persona:p1")
    resolver = SlotResolver(store, scheme=CARD_SCHEME)
    stmt = "有来访者常问退款时效"
    out = resolver.apply(
        SlotAction(
            action="new",
            statement=stmt,
            category="audience",
            origin="external",
            confidence=0.5,
            slot_hint="audience.refund",
        ),
        conversation_id="c1",
    )
    assert out["fact"]["status"] == "candidate"
    assert initial_status("external") == "candidate"
    assert ORIGIN_RANK["external"] < ORIGIN_RANK["inferred"]

    fact_id = out["fact"]["id"]
    resolver.apply(
        SlotAction(
            action="merge",
            statement=stmt,
            category="audience",
            origin="external",
            confidence=0.5,
            slot_hint="audience.refund",
        ),
        conversation_id="c2",
    )
    fact = store.get_fact(fact_id) or {}
    assert fact.get("status") == "candidate"
    distinct = store.count_distinct_conversation_evidence(fact_id)
    assert distinct == 2
    assert not should_promote(
        fact, distinct_conversations=distinct, evidence_count=distinct
    )

    resolver.apply(
        SlotAction(
            action="merge",
            statement=stmt,
            category="audience",
            origin="external",
            confidence=0.5,
            slot_hint="audience.refund",
        ),
        conversation_id="c3",
    )
    fact = store.get_fact(fact_id) or {}
    assert fact.get("status") == "confirmed"


def test_external_cannot_replace_direct(tmp_path):
    store = MemoryStore(tmp_path / "memory.db", owner_key="role:r1")
    resolver = SlotResolver(store, scheme=CARD_SCHEME)
    resolver.apply(
        SlotAction(
            action="new",
            statement="主人确认的领域上限为每秒 10 次",
            category="domain",
            origin="direct",
            confidence=0.9,
            slot_hint="domain.rate_limit",
        ),
        conversation_id="c1",
    )
    out = resolver.apply(
        SlotAction(
            action="replace",
            statement="外部访客称上限为每秒 20 次",
            category="domain",
            origin="external",
            confidence=0.9,
            slot_hint="domain.rate_limit",
        ),
        conversation_id="c2",
    )
    assert out.get("ok") is True
    confirmed = store.list_confirmed()
    assert len(confirmed) == 1
    assert "10 次" in confirmed[0]["statement"]


def test_direct_can_replace_external(tmp_path):
    store = MemoryStore(tmp_path / "memory.db", owner_key="role:r1")
    resolver = SlotResolver(store, scheme=CARD_SCHEME)
    resolver.apply(
        SlotAction(
            action="new",
            statement="有来访者称默认套餐不含 API",
            category="domain",
            origin="external",
            confidence=0.8,
            slot_hint="domain.api_pack",
        ),
        conversation_id="c1",
    )
    resolver.apply(
        SlotAction(
            action="replace",
            statement="主人确认默认套餐包含 API",
            category="domain",
            origin="direct",
            confidence=0.9,
            slot_hint="domain.api_pack",
        ),
        conversation_id="c2",
    )
    confirmed = store.list_confirmed()
    assert len(confirmed) == 1
    assert "包含 API" in confirmed[0]["statement"]


def test_purge_owner_only_this_scope(tmp_path):
    db = tmp_path / "memory.db"
    a = MemoryStore(db, owner_key="role:a")
    b = MemoryStore(db, owner_key="role:b")
    a.upsert_fact(
        slot_key="domain.one",
        category="domain",
        statement="A",
        normalized_value_hash="h1",
        origin="direct",
        status="confirmed",
    )
    b.upsert_fact(
        slot_key="domain.one",
        category="domain",
        statement="B",
        normalized_value_hash="h2",
        origin="direct",
        status="confirmed",
    )
    assert a.purge_owner() == 1
    assert a.list_confirmed() == []
    assert len(b.list_confirmed()) == 1
