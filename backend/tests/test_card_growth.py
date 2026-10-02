from datetime import datetime, timedelta, timezone

from app.engine.memory.cards import KnowledgeCards, role_scope
from app.engine.memory.resolver import SlotAction
from app.engine.memory.service import MemoryService
from app.engine.memory.store import MemoryStore
from app.engine.roles import RoleStore
from app.storage.repo import KnowledgeRepo
from tests.helpers import make_writer


def _cards(tmp_path) -> tuple[KnowledgeCards, RoleStore]:
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    writer = make_writer(repo, tmp_path)
    owner = MemoryService(
        MemoryStore(tmp_path / "memory.db", owner_key="ws1"), repo, knowledge_writer=writer
    )
    roles = RoleStore(tmp_path / "roles")
    from app.engine.conversations import ConversationStore

    cards = KnowledgeCards(
        tmp_path / "memory.db",
        owner=owner,
        roles=roles,
        conversations=ConversationStore(tmp_path / "conversations"),
    )
    return cards, roles


def _set_last_seen(st: MemoryStore, fact_id: str, days_ago: int):
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    with st._connect() as conn:
        conn.execute(
            "UPDATE memory_facts SET last_seen_at = ?, updated_at = ? WHERE id = ?",
            (ts, ts, fact_id),
        )
        conn.commit()


def test_learn_promoted_beats_revised(tmp_path):
    cards, roles = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    st = cards.store(scope)
    from app.engine.memory.normalize import value_hash

    old_stmt = "旧正文足够长"
    slot = f"domain.topic_{value_hash(old_stmt)[:12]}"
    st.upsert_fact(
        slot_key=slot,
        category="domain",
        statement=old_stmt,
        normalized_value_hash="h0",
        origin="external",
        status="candidate",
        fact_id="c1",
    )
    for i in range(2):
        st.add_session_evidence("c1", f"conv{i}")
    cards.learn(
        scope,
        [
                SlotAction(
                    action="merge",
                    statement="新正文更长一些",
                    category="domain",
                    origin="external",
                    slot_hint=slot,
                )
        ],
        conversation_id="conv2",
    )
    entries = cards.growth.list(scope)
    assert len(entries) == 1
    actions = {it["action"] for it in entries[0]["items"]}
    assert actions == {"promoted"}


def test_fade_and_restore(tmp_path):
    cards, roles = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    st = cards.store(scope)
    st.upsert_fact(
        slot_key="domain.a",
        category="domain",
        statement="会淡出",
        normalized_value_hash="ha",
        origin="direct",
        status="confirmed",
        fact_id="f1",
    )
    _set_last_seen(st, "f1", 181)
    result = cards.maintain(now=datetime.now(timezone.utc))
    assert result["faded"] == 1
    panel = cards.list_panel(scope)
    assert any(c["status"] == "stale" for c in panel)
    counts = cards.panel_counts(scope)
    assert counts["count"] == 0
    assert counts["faded_count"] == 1
    out = cards.restore(scope, "f1")
    assert out["ok"] is True
    assert st.get_fact("f1")["status"] == "confirmed"
    result2 = cards.maintain(now=datetime.now(timezone.utc))
    assert result2["faded"] == 0


def test_stale_revived_on_learn(tmp_path):
    cards, roles = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    st = cards.store(scope)
    from app.engine.memory.normalize import value_hash

    stmt = "复活卡内容足够"
    slot = f"domain.topic_{value_hash(stmt)[:12]}"
    st.upsert_fact(
        slot_key=slot,
        category="domain",
        statement=stmt,
        normalized_value_hash="hr",
        origin="direct",
        status="stale",
        fact_id="r1",
    )
    cards.learn(
        scope,
        [
            SlotAction(
                action="noop",
                statement=stmt,
                category="domain",
                origin="direct",
                slot_hint=slot,
            )
        ],
        conversation_id="c1",
    )
    items = cards.growth.list(scope)[0]["items"]
    assert items[0]["action"] == "revived"


def test_purge_clears_growth(tmp_path):
    cards, roles = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    cards.growth.append(scope, "learned", [{"action": "new", "card_id": "x"}])
    cards.growth.mark_faded(scope, datetime.now(timezone.utc).isoformat())
    cards.store(scope).upsert_fact(
        slot_key="domain.p",
        category="domain",
        statement="删",
        normalized_value_hash="hp",
        origin="direct",
        status="confirmed",
    )
    cards.purge_scope(scope)
    assert cards.growth.list(scope) == []
    assert cards.growth.scope_state(scope)["last_faded_at"] is None


def test_maintain_skips_second_fade_same_day(tmp_path):
    cards, roles = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    st = cards.store(scope)
    st.upsert_fact(
        slot_key="domain.f",
        category="domain",
        statement="淡出",
        normalized_value_hash="hf",
        origin="direct",
        status="confirmed",
        fact_id="f1",
    )
    _set_last_seen(st, "f1", 181)
    now = datetime.now(timezone.utc)
    assert cards.maintain(now=now)["faded"] == 1
    st.set_status("f1", "confirmed")
    _set_last_seen(st, "f1", 181)
    assert cards.maintain(now=now + timedelta(hours=1))["faded"] == 0


def test_maintain_skips_deleted_subject(tmp_path):
    cards, roles = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    cards.store(scope).upsert_fact(
        slot_key="domain.z",
        category="domain",
        statement="孤儿",
        normalized_value_hash="hz",
        origin="direct",
        status="confirmed",
    )
    roles.delete(role["id"])
    assert cards.maintain(now=datetime.now(timezone.utc))["faded"] == 0


def test_growth_entries_conversation_title(tmp_path):
    cards, roles = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    conv = cards.conversations
    cid_titled = conv.create(role_id=role["id"])
    conv.append_exchange(cid_titled, "首条用户消息", {"role": "assistant", "text": "回复"})
    cid_empty = conv.create(role_id=role["id"])
    conv.conn.execute(
        "UPDATE conversations SET title = ? WHERE id = ?",
        ("", cid_empty),
    )
    conv.conn.commit()
    cards.growth.append(
        scope,
        "learned",
        [{"action": "new", "card_id": "x"}],
        conversation_id=cid_titled,
    )
    cards.growth.append(
        scope,
        "learned",
        [{"action": "new", "card_id": "y"}],
        conversation_id=cid_empty,
    )
    cards.growth.append(
        scope,
        "learned",
        [{"action": "new", "card_id": "z"}],
        conversation_id="deleted-conv",
    )
    by_cid = {
        e["conversation_id"]: e["conversation_title"]
        for e in cards.growth_entries(scope)
    }
    assert by_cid[cid_titled] == "首条用户消息"
    assert by_cid[cid_empty] == ""
    assert by_cid["deleted-conv"] is None


def test_http_growth_restore_counts(client):
    container = client.app.state.container
    role = container.roles.create(name="G", system_prompt="")
    scope = role_scope(role["id"])
    st = container.knowledge_cards.store(scope)
    st.upsert_fact(
        slot_key="domain.g",
        category="domain",
        statement="已确认",
        normalized_value_hash="hg1",
        origin="direct",
        status="confirmed",
        fact_id="g1",
    )
    st.upsert_fact(
        slot_key="domain.s",
        category="domain",
        statement="已淡出",
        normalized_value_hash="hg2",
        origin="direct",
        status="stale",
        fact_id="g2",
    )
    listed = client.get("/api/cards", params={"scope": scope}).json()
    assert listed["count"] == 1
    assert listed["faded_count"] == 1
    assert any(c["status"] == "stale" for c in listed["cards"])
    container.knowledge_cards.growth.append(
        scope,
        "learned",
        [{"action": "new", "card_id": "g1", "statement": "已确认"}],
        conversation_id="c1",
    )
    growth = client.get("/api/cards/growth", params={"scope": scope}).json()
    assert growth["entries"][0]["items"][0]["action"] == "new"
    bad = client.post("/api/cards/g1/restore", params={"scope": scope})
    assert bad.status_code == 400
    ok = client.post("/api/cards/g2/restore", params={"scope": scope})
    assert ok.status_code == 200
