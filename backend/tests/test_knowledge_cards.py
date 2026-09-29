from datetime import datetime, timedelta, timezone

from app.engine.conversations import ConversationStore
from app.engine.memory.cards import KnowledgeCards, persona_scope, role_scope
from app.engine.memory.service import MemoryService
from app.engine.memory.store import MemoryStore
from app.engine.roles import RoleStore, VISIBILITY_HIDDEN
from app.storage.repo import KnowledgeRepo
from tests.helpers import make_writer


def _cards(tmp_path) -> tuple[KnowledgeCards, RoleStore, MemoryService]:
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    writer = make_writer(repo, tmp_path)
    owner_store = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    owner = MemoryService(owner_store, repo, knowledge_writer=writer)
    roles = RoleStore(tmp_path / "roles")
    conv = ConversationStore(tmp_path / "conversations")
    cards = KnowledgeCards(
        tmp_path / "memory.db",
        owner=owner,
        roles=roles,
        conversations=conv,
        channel_instances=_FakeChannelInstances(),
    )
    return cards, roles, owner


class _FakeChannelInstances:
    def __init__(self):
        self._items = {}

    def put(self, inst: dict):
        self._items[inst["id"]] = inst

    def get(self, instance_id: str) -> dict:
        if instance_id not in self._items:
            raise KeyError(instance_id)
        return self._items[instance_id]


def test_scope_for_role(tmp_path):
    cards, roles, _ = _cards(tmp_path)
    sidebar = roles.create(name="编辑", system_prompt="你是编辑")
    persona = roles.create_persona(name="共用客服", system_prompt="客服")
    hidden = roles.create(
        name="通道角色",
        system_prompt="hidden",
        visibility=VISIBILITY_HIDDEN,
        persona_id=persona["id"],
    )
    assert cards.scope_for_role(sidebar["id"]) == role_scope(sidebar["id"])
    assert cards.scope_for_role(hidden["id"]) == persona_scope(persona["id"])
    assert cards.scope_for_role(
        roles.create(name="无人设隐藏", visibility=VISIBILITY_HIDDEN)["id"]
    ) is None
    assert cards.scope_for_role("missing") is None


def test_lenses_for_owner_dm_and_channel(tmp_path):
    cards, roles, _ = _cards(tmp_path)
    conv = cards.conversations
    role = roles.create(name="策划", system_prompt="策划助手")
    cid_owner = conv.create(role_id=role["id"])
    owner_lens, card_lens = cards.lenses_for(cid_owner)
    assert owner_lens is True
    assert card_lens is not None
    assert card_lens.origin == "direct"
    assert card_lens.scope == role_scope(role["id"])

    persona = roles.create_persona(name="API 人设", system_prompt="API")
    inst_id = "inst1"
    cards.channel_instances.put(
        {
            "id": inst_id,
            "persona_id": persona["id"],
            "include_owner_memory": False,
        }
    )
    cid_ch = conv.create(
        role_id=role["id"],
        origin="api",
        channel_instance_id=inst_id,
    )
    owner_lens, card_lens = cards.lenses_for(cid_ch)
    assert owner_lens is False
    assert card_lens is not None
    assert card_lens.origin == "external"
    assert card_lens.scope == persona_scope(persona["id"])

    cid_peer = conv.create(role_id=role["id"])
    conv.conn.execute(
        "UPDATE conversations SET kind = ? WHERE id = ?",
        ("peer_dm", cid_peer),
    )
    conv.conn.commit()
    assert cards.lenses_for(cid_peer) == (False, None)


def test_render_grouping_and_truncation(tmp_path):
    cards, roles, _ = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    st = cards.store(scope)
    st.upsert_fact(
        slot_key="lesson.a",
        category="lesson",
        statement="经验一",
        normalized_value_hash="h1",
        origin="direct",
        status="confirmed",
    )
    st.upsert_fact(
        slot_key="domain.b",
        category="domain",
        statement="外部事实",
        normalized_value_hash="h2",
        origin="external",
        status="confirmed",
    )
    st.upsert_fact(
        slot_key="practice.c",
        category="practice",
        statement="待印证做法",
        normalized_value_hash="h3",
        origin="direct",
        status="candidate",
    )
    text = cards.render(scope)
    assert text.index("## 领域知识") < text.index("## 经验")
    assert "（外部来源）" in text
    assert "待印证" not in text

    role2 = roles.create(name="R2", system_prompt="")
    scope2 = role_scope(role2["id"])
    tiny = KnowledgeCards(
        tmp_path / "memory.db",
        owner=cards.owner,
        roles=roles,
        max_chars=28,
    )
    st2 = tiny.store(scope2)
    for i in range(4):
        st2.upsert_fact(
            slot_key=f"domain.x{i}",
            category="domain",
            statement=f"短条目{i}",
            normalized_value_hash=f"h{i}x",
            origin="direct",
            status="confirmed",
        )
    truncated = tiny.render(scope2)
    assert len(truncated) <= 28
    assert truncated.count("- ") >= 1
    assert "短条目3" in truncated
    assert "短条目0" not in truncated


def test_injection_for_channel_owner_memory(tmp_path):
    cards, roles, owner = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    owner_store = owner.store
    owner_store.upsert_fact(
        slot_key="preference.x",
        category="preference",
        statement="主人偏好简洁",
        normalized_value_hash="oh",
        origin="direct",
        status="confirmed",
    )
    inst_id = "i1"
    cards.channel_instances.put({"id": inst_id, "persona_id": "p0"})
    cid = cards.conversations.create(
        role_id=role["id"], origin="api", channel_instance_id=inst_id
    )
    inj = cards.injection_for(conversation_id=cid, role_id=role["id"])
    assert inj.owner_memory == ""
    cards.channel_instances.put(
        {"id": inst_id, "persona_id": "p0", "include_owner_memory": True}
    )
    inj2 = cards.injection_for(conversation_id=cid, role_id=role["id"])
    assert "简洁" in inj2.owner_memory

    cid_web = cards.conversations.create(role_id=role["id"])
    inj3 = cards.injection_for(conversation_id=cid_web, role_id=role["id"])
    assert "简洁" in inj3.owner_memory


def test_resolve_subject_hidden_role_by_id(tmp_path):
    cards, roles, _ = _cards(tmp_path)
    persona = roles.create_persona(name="共用", system_prompt="")
    hidden = roles.create(
        name="通道",
        system_prompt="",
        visibility=VISIBILITY_HIDDEN,
        persona_id=persona["id"],
    )
    assert cards.resolve_subject(hidden["id"]) == persona_scope(persona["id"])


def test_render_no_dangling_header(tmp_path):
    cards, roles, _ = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    cards.store(scope).upsert_fact(
        slot_key="domain.long",
        category="domain",
        statement="这是一条放不进预算的长条目内容",
        normalized_value_hash="hl",
        origin="direct",
        status="confirmed",
    )
    tiny = KnowledgeCards(
        tmp_path / "memory.db",
        owner=cards.owner,
        roles=roles,
        max_chars=10,
    )
    text = tiny.render(scope)
    assert text == ""
    assert "##" not in text


def test_render_origin_weight_over_recency(tmp_path):
    cards, roles, _ = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    st = cards.store(scope)
    older = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    newer = datetime.now(timezone.utc).isoformat()
    st.upsert_fact(
        slot_key="domain.direct_old",
        category="domain",
        statement="较旧 direct 卡",
        normalized_value_hash="hd",
        origin="direct",
        confidence=0.9,
        status="confirmed",
    )
    with st._connect() as conn:
        conn.execute(
            "UPDATE memory_facts SET updated_at = ? WHERE slot_key = ?",
            (older, "domain.direct_old"),
        )
        conn.commit()
    st.upsert_fact(
        slot_key="domain.external_new",
        category="domain",
        statement="较新 external 卡",
        normalized_value_hash="he",
        origin="external",
        confidence=0.9,
        status="confirmed",
    )
    with st._connect() as conn:
        conn.execute(
            "UPDATE memory_facts SET updated_at = ? WHERE slot_key = ?",
            (newer, "domain.external_new"),
        )
        conn.commit()
    text = cards.render(scope)
    assert text.index("较旧 direct 卡") < text.index("较新 external 卡")


def test_render_newer_first_same_origin_and_confidence(tmp_path):
    cards, roles, _ = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    st = cards.store(scope)
    older = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    newer = datetime.now(timezone.utc).isoformat()
    st.upsert_fact(
        slot_key="domain.old",
        category="domain",
        statement="旧条目",
        normalized_value_hash="ho",
        origin="direct",
        confidence=0.9,
        status="confirmed",
    )
    with st._connect() as conn:
        conn.execute(
            "UPDATE memory_facts SET updated_at = ? WHERE slot_key = ?",
            (older, "domain.old"),
        )
        conn.commit()
    st.upsert_fact(
        slot_key="domain.new",
        category="domain",
        statement="新条目",
        normalized_value_hash="hn",
        origin="direct",
        confidence=0.9,
        status="confirmed",
    )
    with st._connect() as conn:
        conn.execute(
            "UPDATE memory_facts SET updated_at = ? WHERE slot_key = ?",
            (newer, "domain.new"),
        )
        conn.commit()
    text = cards.render(scope)
    assert text.index("新条目") < text.index("旧条目")


def test_scopes_isolated_and_purge(tmp_path):
    cards, roles, _ = _cards(tmp_path)
    r1 = roles.create(name="A", system_prompt="")
    r2 = roles.create(name="B", system_prompt="")
    s1 = role_scope(r1["id"])
    s2 = role_scope(r2["id"])
    cards.store(s1).upsert_fact(
        slot_key="domain.a",
        category="domain",
        statement="A 卡",
        normalized_value_hash="a",
        origin="direct",
        status="confirmed",
    )
    cards.store(s2).upsert_fact(
        slot_key="domain.b",
        category="domain",
        statement="B 卡",
        normalized_value_hash="b",
        origin="direct",
        status="confirmed",
    )
    assert len(cards.list_panel(s1)) == 1
    assert len(cards.list_panel(s2)) == 1
    assert cards.purge_scope(s1) == 1
    assert cards.list_panel(s1) == []
    assert len(cards.list_panel(s2)) == 1
