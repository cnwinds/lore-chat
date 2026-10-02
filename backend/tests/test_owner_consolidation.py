import json
from datetime import datetime, timedelta, timezone

from app.engine.memory.card_consolidation import (
    LLMCardConsolidator,
    OWNER_PROFILE,
    _OWNER_SYSTEM_PROMPT,
)
from app.engine.memory.cards import KnowledgeCards, OWNER_SCOPE, role_scope
from app.engine.memory.decay import DecayConfig
from app.engine.memory.normalize import value_hash
from app.engine.memory.resolver import SlotAction
from app.engine.memory.service import MemoryService
from app.engine.memory.store import MemoryStore
from app.engine.memory_maintenance import MemoryMaintenanceJob
from app.engine.memory_worker import MemoryWorker
from app.engine.roles import RoleStore
from app.storage.repo import KnowledgeRepo
from tests.helpers import make_writer, preference_action, scripted_memory_extractor


class FakeLLM:
    def __init__(self, payload: str | dict):
        self.payload = payload
        self.last_messages = None

    def chat(self, messages, **_kwargs):
        self.last_messages = messages
        if isinstance(self.payload, str):
            return self.payload
        return json.dumps(self.payload, ensure_ascii=False)


def _ops(items: list[dict]):
    return {"ops": items}


def _owner_setup(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    writer = make_writer(repo, tmp_path)
    owner = MemoryService(
        MemoryStore(tmp_path / "memory.db", owner_key="ws1"), repo, knowledge_writer=writer
    )
    roles = RoleStore(tmp_path / "roles")
    cards = KnowledgeCards(tmp_path / "memory.db", owner=owner, roles=roles)
    return cards, owner, roles


def _seed_owner(
    st: MemoryStore,
    *,
    fact_id: str,
    statement: str,
    vhash: str | None = None,
    origin="inferred",
    status="confirmed",
    slot_key=None,
    kind="preference",
):
    st.upsert_fact(
        slot_key=slot_key or f"{kind}.topic_{fact_id}",
        category=kind,
        statement=statement,
        normalized_value_hash=vhash or value_hash(statement),
        origin=origin,
        status=status,
        fact_id=fact_id,
    )


def _short_map(st: MemoryStore) -> dict[str, dict]:
    facts = st.list_confirmed() + st.list_candidates()
    facts.sort(key=lambda f: f.get("updated_at") or "", reverse=True)
    return {f"c{i + 1}": f for i, f in enumerate(facts)}


def _seed_card(
    st: MemoryStore,
    *,
    fact_id: str,
    statement: str,
    vhash: str | None = None,
    kind="lesson",
):
    st.upsert_fact(
        slot_key=f"{kind}.topic_{fact_id}",
        category=kind,
        statement=statement,
        normalized_value_hash=vhash or value_hash(statement),
        origin="direct",
        status="confirmed",
        fact_id=fact_id,
    )


def _short_ids(st: MemoryStore, *fact_ids: str) -> list[str]:
    short = _short_map(st)
    inv = {v["id"]: k for k, v in short.items()}
    return [inv[fid] for fid in fact_ids]


def test_owner_merge_two_preference(tmp_path):
    cards, owner, _ = _owner_setup(tmp_path)
    st = owner.store
    _seed_owner(st, fact_id="a", statement="主人偏好简洁回答", origin="inferred")
    _seed_owner(st, fact_id="b", statement="主人喜欢简洁直接的回答", vhash="hb")
    c_a, c_b = _short_ids(st, "a", "b")
    llm = FakeLLM(
        _ops(
            [
                {
                    "op": "merge",
                    "ids": [c_a, c_b],
                    "kind": "preference",
                    "statement": "主人偏好简洁直接的回答",
                }
            ]
        )
    )
    cards.owner_consolidator = LLMCardConsolidator(llm, cards, profile=OWNER_PROFILE)
    assert cards.owner_consolidator.run(OWNER_SCOPE, None)["ops_applied"] == 1
    kept = st.get_fact("a")
    assert kept["statement"] == "主人偏好简洁直接的回答"
    assert st.get_fact("b")["status"] == "superseded"
    entry = cards.growth.list(OWNER_SCOPE)[0]
    assert entry["kind"] == "consolidated"
    item = entry["items"][0]
    assert item == {
        "action": "merged",
        "card_id": "a",
        "kind": "preference",
        "statement": "主人偏好简洁直接的回答",
        "external": False,
        "status": "confirmed",
        "previous": "主人偏好简洁回答",
        "sources": [{"card_id": "b", "statement": "主人喜欢简洁直接的回答"}],
    }


def test_owner_readonly_merge_and_qualify_and_supersede(tmp_path):
    cards, owner, _ = _owner_setup(tmp_path)
    st = owner.store
    _seed_owner(st, fact_id="m", statement="主人亲定内容", origin="manual")
    _seed_owner(st, fact_id="i", statement="推断内容甲", vhash="hi")
    _seed_owner(st, fact_id="e", statement="要求记住内容", origin="explicit_remember", vhash="he")
    _seed_owner(st, fact_id="x", statement="推断内容乙", vhash="hx")

    for readonly_id, other_id in (("m", "i"), ("e", "x")):
        c_ro, c_other = _short_ids(st, readonly_id, other_id)
        llm = FakeLLM(
            _ops(
                [
                    {
                        "op": "merge",
                        "ids": [c_ro, c_other],
                        "statement": "合并后的正文足够长",
                    }
                ]
            )
        )
        cards.owner_consolidator = LLMCardConsolidator(llm, cards, profile=OWNER_PROFILE)
        dropped = cards.owner_consolidator.run(OWNER_SCOPE, None)["dropped"]
        assert dropped == [(0, "G4_manual_readonly")]

    ce, ci = _short_ids(st, "e", "i")
    llm2 = FakeLLM(
        _ops([{"op": "qualify", "ids": [ce, ci], "rewrite": {ce: "新正文足够长"}}])
    )
    cards.owner_consolidator = LLMCardConsolidator(llm2, cards, profile=OWNER_PROFILE)
    dropped2 = cards.owner_consolidator.run(OWNER_SCOPE, None)["dropped"]
    assert dropped2 == [(0, "G4_manual_readonly")]
    assert st.get_fact("e")["statement"] == "要求记住内容"

    _seed_owner(st, fact_id="o1", statement="旧说法内容", vhash="ho1")
    _seed_owner(
        st,
        fact_id="o2",
        statement="新说法内容",
        origin="explicit_remember",
        vhash="ho2",
    )
    with st._connect() as conn:
        conn.execute(
            "UPDATE memory_facts SET last_seen_at = ? WHERE id = ?",
            ("2026-09-02T00:00:00+00:00", "o1"),
        )
        conn.execute(
            "UPDATE memory_facts SET last_seen_at = ? WHERE id = ?",
            ("2026-09-01T00:00:00+00:00", "o2"),
        )
        conn.commit()
    c1, c2 = _short_ids(st, "o1", "o2")
    llm3 = FakeLLM(_ops([{"op": "supersede", "ids": [c1, c2]}]))
    cards.owner_consolidator = LLMCardConsolidator(llm3, cards, profile=OWNER_PROFILE)
    dropped3 = cards.owner_consolidator.run(OWNER_SCOPE, None)["dropped"]
    assert dropped3 == [(0, "G4_manual_loser")]


def test_owner_kind_not_in_sources_and_default_keeper(tmp_path):
    cards, owner, _ = _owner_setup(tmp_path)
    st = owner.store
    _seed_owner(st, fact_id="g", statement="长期目标内容", kind="goal")
    _seed_owner(st, fact_id="p", statement="偏好内容足够", kind="preference", vhash="hp")
    c_g, c_p = _short_ids(st, "g", "p")
    llm = FakeLLM(
        _ops(
            [
                {
                    "op": "merge",
                    "ids": [c_g, c_p],
                    "kind": "identity",
                    "statement": "合并正文足够长",
                }
            ]
        )
    )
    cards.owner_consolidator = LLMCardConsolidator(llm, cards, profile=OWNER_PROFILE)
    assert cards.owner_consolidator.run(OWNER_SCOPE, None)["dropped"] == [
        (0, "G6_kind_not_in_sources")
    ]

    llm2 = FakeLLM(
        _ops(
            [
                {
                    "op": "merge",
                    "ids": [c_g, c_p],
                    "statement": "合并正文足够长",
                }
            ]
        )
    )
    cards.owner_consolidator = LLMCardConsolidator(llm2, cards, profile=OWNER_PROFILE)
    assert cards.owner_consolidator.run(OWNER_SCOPE, None)["ops_applied"] == 1
    kept = st.get_fact("g")
    assert (kept["category"], kept["statement"]) == ("goal", "合并正文足够长")
    assert st.get_fact("p")["status"] == "superseded"


def test_owner_sensitive_gate(tmp_path):
    cards, owner, _ = _owner_setup(tmp_path)
    st = owner.store
    _seed_owner(st, fact_id="a", statement="推断甲内容足够", origin="inferred")
    _seed_owner(st, fact_id="b", statement="推断乙内容足够", vhash="hb", origin="inferred")
    c_a, c_b = _short_ids(st, "a", "b")
    llm = FakeLLM(
        _ops(
            [
                {
                    "op": "merge",
                    "ids": [c_a, c_b],
                    "kind": "preference",
                    "statement": "我的工资是一万元",
                }
            ]
        )
    )
    cards.owner_consolidator = LLMCardConsolidator(llm, cards, profile=OWNER_PROFILE)
    assert cards.owner_consolidator.run(OWNER_SCOPE, None)["dropped"] == [
        (0, "G8_sensitive")
    ]

    _seed_owner(st, fact_id="d1", statement="自述甲内容足够", origin="direct", vhash="hd1")
    _seed_owner(st, fact_id="d2", statement="自述乙内容足够", origin="direct", vhash="hd2")
    c_d1, c_d2 = _short_ids(st, "d1", "d2")
    llm2 = FakeLLM(
        _ops(
            [
                {
                    "op": "merge",
                    "ids": [c_d1, c_d2],
                    "kind": "preference",
                    "statement": "我的工资是一万元",
                }
            ]
        )
    )
    cards.owner_consolidator = LLMCardConsolidator(llm2, cards, profile=OWNER_PROFILE)
    assert cards.owner_consolidator.run(OWNER_SCOPE, None)["dropped"] == [
        (0, "G8_sensitive")
    ]

    _seed_owner(st, fact_id="q1", statement="条件甲内容足够", vhash="hq1")
    _seed_owner(st, fact_id="q2", statement="条件乙内容足够", vhash="hq2")
    cq1, cq2 = _short_ids(st, "q1", "q2")
    llm3 = FakeLLM(
        _ops(
            [
                {
                    "op": "qualify",
                    "ids": [cq1, cq2],
                    "rewrite": {cq1: "我住在北京市朝阳区某某路100号"},
                }
            ]
        )
    )
    cards.owner_consolidator = LLMCardConsolidator(llm3, cards, profile=OWNER_PROFILE)
    assert cards.owner_consolidator.run(OWNER_SCOPE, None)["dropped"] == [
        (0, "G8_sensitive")
    ]


def test_owner_abstract_slot_owner_scheme(tmp_path):
    cards, owner, _ = _owner_setup(tmp_path)
    st = owner.store
    hint_slot = "workflow.team_sync"
    _seed_owner(st, fact_id="a", statement="主人的部署脚本放在仓库根目录", kind="workflow")
    _seed_owner(
        st,
        fact_id="b",
        statement="主人的数据脚本单独放一处",
        kind="workflow",
        vhash="hb",
    )
    c_a, c_b = _short_ids(st, "a", "b")
    llm = FakeLLM(
        _ops(
            [
                {
                    "op": "abstract",
                    "ids": [c_a, c_b],
                    "kind": "workflow",
                    "slot_key": hint_slot,
                    "statement": "主人习惯把脚本文件放在 scripts 目录",
                }
            ]
        )
    )
    cards.owner_consolidator = LLMCardConsolidator(llm, cards, profile=OWNER_PROFILE)
    assert cards.owner_consolidator.run(OWNER_SCOPE, None)["ops_applied"] == 1
    new_facts = [f for f in st.list_active_facts() if f["id"] not in ("a", "b")]
    assert len(new_facts) == 1
    assert new_facts[0]["slot_key"] == "workflow.script_layout"

    _seed_owner(
        st,
        fact_id="block",
        statement="已有活跃协作记忆",
        kind="workflow",
        slot_key=hint_slot,
        vhash="hblock",
    )
    _seed_owner(st, fact_id="c", statement="第三段协作内容", kind="workflow", vhash="hc")
    _seed_owner(st, fact_id="d", statement="第四段协作内容", kind="workflow", vhash="hd")
    c_c, c_d = _short_ids(st, "c", "d")
    stmt = "主人按时段安排协作方式二"
    llm2 = FakeLLM(
        _ops(
            [
                {
                    "op": "abstract",
                    "ids": [c_c, c_d],
                    "kind": "workflow",
                    "slot_key": hint_slot,
                    "statement": stmt,
                }
            ]
        )
    )
    cards.owner_consolidator = LLMCardConsolidator(llm2, cards, profile=OWNER_PROFILE)
    assert cards.owner_consolidator.run(OWNER_SCOPE, None)["ops_applied"] == 1
    created = [
        f
        for f in st.list_active_facts()
        if f.get("statement") == stmt and f["status"] in ("confirmed", "candidate")
    ]
    assert len(created) == 1
    assert created[0]["slot_key"] == f"workflow.topic_{value_hash(stmt)[:12]}"


def test_owner_user_message_verbatim(tmp_path):
    cards, owner, _ = _owner_setup(tmp_path)
    st = owner.store
    _seed_owner(st, fact_id="c1", statement="偏好正文内容足够")
    st.add_session_evidence("c1", "s1")
    st.add_session_evidence("c1", "s2")
    with st._connect() as conn:
        conn.execute(
            "UPDATE memory_facts SET last_seen_at = ?, updated_at = ? WHERE id = ?",
            ("2026-09-01T00:00:00+00:00", "2026-09-02T00:00:00+00:00", "c1"),
        )
        conn.commit()
    _seed_owner(st, fact_id="c2", statement="另一段偏好内容", vhash="hc2")
    with st._connect() as conn:
        conn.execute(
            "UPDATE memory_facts SET updated_at = ?, last_seen_at = ? WHERE id = ?",
            ("2026-09-01T00:00:00+00:00", "", "c2"),
        )
        conn.commit()
    llm = FakeLLM(_ops([]))
    cards.owner_consolidator = LLMCardConsolidator(llm, cards, profile=OWNER_PROFILE)
    cards.owner_consolidator.run(OWNER_SCOPE, None)
    assert llm.last_messages[0]["content"] == _OWNER_SYSTEM_PROMPT
    assert llm.last_messages[1]["content"] == (
        "主人记忆（编号｜种类｜来源｜状态｜出处会话数｜最近出处｜正文）：\n"
        "- c1｜preference｜对话推断｜已确认｜2 段｜2026-09-01｜偏好正文内容足够\n"
        "- c2｜preference｜对话推断｜已确认｜0 段｜｜另一段偏好内容"
    )


class _IndexSpy:
    def __init__(self):
        self.calls: list[str] = []

    def sync_scope_locked(self, scope: str) -> None:
        self.calls.append(scope)


def test_maintain_owner_consolidation_budget_and_no_index(tmp_path):
    cards, owner, roles = _owner_setup(tmp_path)
    st = owner.store
    _seed_owner(st, fact_id="oa", statement="主人记忆甲内容")
    _seed_owner(st, fact_id="ob", statement="主人记忆乙内容", vhash="hob")
    spy = _IndexSpy()
    cards.index = spy  # type: ignore[assignment]
    llm = FakeLLM(_ops([]))
    cards.owner_consolidator = LLMCardConsolidator(llm, cards, profile=OWNER_PROFILE)
    cards.consolidator = LLMCardConsolidator(llm, cards)
    now = datetime(2027, 6, 1, tzinfo=timezone.utc)
    assert cards.maintain(now=now, max_consolidations=3)["consolidated_scopes"] == 1
    assert cards.growth.scope_state(OWNER_SCOPE)["last_consolidated_at"] is not None

    class FailLLM:
        def chat(self, *_a, **_k):
            raise RuntimeError("should not call")

    cards.owner_consolidator = LLMCardConsolidator(FailLLM(), cards, profile=OWNER_PROFILE)
    assert cards.maintain(now=now, max_consolidations=3)["consolidated_scopes"] == 0
    assert "owner" not in spy.calls

    for i in range(3):
        role = roles.create(name=f"R{i}", system_prompt="x")
        scope = role_scope(role["id"])
        cst = cards.store(scope)
        cst.upsert_fact(
            slot_key=f"lesson.topic_a{i}",
            category="lesson",
            statement=f"A{i}内容足够长",
            normalized_value_hash=f"ha{i}",
            origin="direct",
            status="confirmed",
            fact_id=f"a{i}",
        )
        cst.upsert_fact(
            slot_key=f"lesson.topic_b{i}",
            category="lesson",
            statement=f"B{i}内容足够长",
            normalized_value_hash=f"hb{i}",
            origin="direct",
            status="confirmed",
            fact_id=f"b{i}",
        )
    class CountLLM:
        calls = 0

        def chat(self, *_a, **_k):
            CountLLM.calls += 1
            return json.dumps(_ops([]))

    cards3, owner3, roles3 = _owner_setup(tmp_path / "maint3")
    st3 = owner3.store
    _seed_owner(st3, fact_id="oa3", statement="主人记忆甲内容三")
    _seed_owner(st3, fact_id="ob3", statement="主人记忆乙内容三", vhash="hob3")
    with st3._connect() as conn:
        conn.execute(
            "UPDATE memory_facts SET updated_at = ? WHERE id IN (?, ?)",
            ((now + timedelta(minutes=1)).isoformat(), "oa3", "ob3"),
        )
        conn.commit()
    cards3.growth.mark_consolidated(
        OWNER_SCOPE, (now - timedelta(hours=30)).isoformat()
    )
    for i in range(3):
        role = roles3.create(name=f"S{i}", system_prompt="x")
        scope = role_scope(role["id"])
        cst = cards3.store(scope)
        _seed_card(
            cst,
            fact_id=f"sa{i}",
            statement=f"SA{i}内容足够长",
            kind="lesson",
        )
        _seed_card(
            cst,
            fact_id=f"sb{i}",
            statement=f"SB{i}内容足够长",
            vhash=f"hsb{i}",
            kind="lesson",
        )
        with cst._connect() as conn:
            conn.execute(
                "UPDATE memory_facts SET last_seen_at = ?, updated_at = ? WHERE owner_key = ?",
                (now.isoformat(), now.isoformat(), scope),
            )
            conn.commit()
    assert len(cards3.list_scopes()) == 3
    for sc in cards3.list_scopes():
        assert cards3.subject_for_scope(sc) is not None
    count_llm = CountLLM()
    cards3.owner_consolidator = LLMCardConsolidator(
        count_llm, cards3, profile=OWNER_PROFILE
    )
    cards3.consolidator = LLMCardConsolidator(count_llm, cards3)
    result = cards3.maintain(now=now, max_consolidations=1)
    assert result["consolidated_scopes"] == 1
    assert CountLLM.calls == 1
    for sc in cards3.list_scopes():
        assert cards3.growth.scope_state(sc)["last_consolidated_at"] is None

    CountLLM.calls = 0
    owner_prev = (now - timedelta(hours=30)).isoformat()
    cards3.growth.mark_consolidated(OWNER_SCOPE, owner_prev)
    result3 = cards3.maintain(now=now, max_consolidations=3)
    assert result3["consolidated_scopes"] == 3
    assert CountLLM.calls == 3
    assert cards3.growth.scope_state(OWNER_SCOPE)["last_consolidated_at"] != owner_prev
    role_done = [
        sc
        for sc in cards3.list_scopes()
        if cards3.growth.scope_state(sc)["last_consolidated_at"] is not None
    ]
    assert len(role_done) == 2

    cards4, owner4, roles4 = _owner_setup(tmp_path / "maint4")
    for i in range(3):
        role = roles4.create(name=f"T{i}", system_prompt="x")
        scope = role_scope(role["id"])
        cst = cards4.store(scope)
        _seed_card(cst, fact_id=f"ta{i}", statement=f"TA{i}内容足够长", kind="lesson")
        _seed_card(
            cst, fact_id=f"tb{i}", statement=f"TB{i}内容足够长", vhash=f"htb{i}", kind="lesson"
        )
        with cst._connect() as conn:
            conn.execute(
                "UPDATE memory_facts SET last_seen_at = ?, updated_at = ? WHERE owner_key = ?",
                (now.isoformat(), now.isoformat(), scope),
            )
            conn.commit()
    CountLLM.calls = 0
    cards4.consolidator = LLMCardConsolidator(CountLLM(), cards4)
    result4 = cards4.maintain(now=now, max_consolidations=3)
    assert result4["consolidated_scopes"] == 3
    assert CountLLM.calls == 3


def test_learn_owner_growth_items(tmp_path):
    cards, owner, _ = _owner_setup(tmp_path)
    st = owner.store
    cid = "conv-learn"
    new = SlotAction(
        action="new",
        statement="新学记忆内容足够长",
        category="preference",
        origin="direct",
        slot_hint="preference.new_topic",
    )
    cards.learn_owner([new], conversation_id=cid)
    fid = st.list_confirmed()[0]["id"]
    slot = st.list_confirmed()[0]["slot_key"]
    cand = st.upsert_fact(
        slot_key="preference.cand",
        category="preference",
        statement="待转正记忆内容",
        normalized_value_hash=value_hash("待转正记忆内容"),
        origin="inferred",
        status="candidate",
        fact_id="cand1",
    )
    for sess in ("s-prom-1", "s-prom-2", "s-prom-3"):
        cards.learn_owner(
            [
                SlotAction(
                    action="noop",
                    statement="待转正记忆内容",
                    category="preference",
                    origin="inferred",
                    slot_hint="preference.cand",
                )
            ],
            conversation_id=sess,
        )
    cards.learn_owner(
        [
            SlotAction(
                action="merge",
                statement="修正后的记忆内容",
                category="preference",
                origin="direct",
                slot_hint=slot,
            )
        ],
        conversation_id=cid,
    )
    entries = cards.growth.list(OWNER_SCOPE)
    learned = sorted(
        [e for e in entries if e["kind"] == "learned"],
        key=lambda e: e["created_at"],
    )
    assert len(learned) == 3
    assert learned[0]["conversation_id"] == cid
    assert learned[0]["items"] == [
        {
            "action": "new",
            "card_id": fid,
            "kind": "preference",
            "statement": "新学记忆内容足够长",
            "external": False,
            "status": "confirmed",
        }
    ]
    assert learned[1]["items"] == [
        {
            "action": "promoted",
            "card_id": cand["id"],
            "kind": "preference",
            "statement": "待转正记忆内容",
            "external": False,
            "status": "confirmed",
        }
    ]
    assert learned[2]["conversation_id"] == cid
    assert learned[2]["items"] == [
        {
            "action": "revised",
            "card_id": fid,
            "kind": "preference",
            "statement": "修正后的记忆内容",
            "external": False,
            "status": "confirmed",
            "previous": "新学记忆内容足够长",
        }
    ]


def test_session_observe_owner_learned_growth(tmp_path, monkeypatch):
    from app.engine.conversations import ConversationStore

    conv = ConversationStore(tmp_path / "conversations")
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    mem = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    svc = MemoryService(mem, repo, knowledge_writer=make_writer(repo, tmp_path))
    roles = RoleStore(tmp_path / "roles")
    cards = KnowledgeCards(tmp_path / "memory.db", owner=svc, roles=roles)
    worker = MemoryWorker(
        conv,
        svc,
        extractor=scripted_memory_extractor(preference_action("我偏好简洁回答")),
        cards=cards,
        idle_hours=0,
    )
    cid = conv.create()
    conv.begin_turn(cid, "我偏好简洁回答", "c1", observation_allowed=True)
    past = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    conv.conn.execute(
        "UPDATE conversations SET last_user_message_at = ? WHERE id = ?",
        (past, cid),
    )
    conv.conn.commit()
    worker.drain(max_jobs=5)
    learned = [e for e in cards.growth.list(OWNER_SCOPE) if e["kind"] == "learned"]
    fact = mem.list_active_facts()[0]
    assert [(e["conversation_id"], e["items"]) for e in learned] == [
        (
            cid,
            [
                {
                    "action": "new",
                    "card_id": fact["id"],
                    "kind": fact["category"],
                    "statement": "我偏好简洁回答",
                    "external": False,
                    "status": fact["status"],
                }
            ],
        )
    ]


def test_memory_decay_growth_faded(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    writer = make_writer(repo, tmp_path)
    st = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    cards = KnowledgeCards(tmp_path / "memory.db", owner=MemoryService(st, repo, knowledge_writer=writer), roles=RoleStore(tmp_path / "roles"))
    old = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
    st.upsert_fact(
        slot_key="goal.old",
        category="goal",
        statement="过期目标内容足够",
        normalized_value_hash=value_hash("过期目标内容足够"),
        origin="direct",
        status="confirmed",
        fact_id="f_stale",
    )
    st.upsert_fact(
        slot_key="preference.cand_old",
        category="preference",
        statement="过期候选内容足够",
        normalized_value_hash=value_hash("过期候选内容足够"),
        origin="inferred",
        status="candidate",
        fact_id="f_reject",
    )
    st.upsert_fact(
        slot_key="preference.dem",
        category="preference",
        statement="降级推断内容足够",
        normalized_value_hash=value_hash("降级推断内容足够"),
        origin="inferred",
        status="confirmed",
        fact_id="f_dem",
    )
    with st._connect() as conn:
        conn.execute(
            "UPDATE memory_facts SET last_seen_at = ?, updated_at = ? WHERE id IN (?, ?, ?)",
            (old, old, "f_stale", "f_reject", "f_dem"),
        )
        conn.commit()
    job = MemoryMaintenanceJob(st, growth=cards.growth, config=DecayConfig())
    job.run()
    items = cards.growth.list(OWNER_SCOPE)[0]["items"]
    assert items == [
        {
            "action": "expired",
            "card_id": "f_stale",
            "kind": "goal",
            "statement": "过期目标内容足够",
            "external": False,
            "status": "stale",
        },
        {
            "action": "dropped",
            "card_id": "f_reject",
            "kind": "preference",
            "statement": "过期候选内容足够",
            "external": False,
            "status": "rejected",
        },
        {
            "action": "demoted",
            "card_id": "f_dem",
            "kind": "preference",
            "statement": "降级推断内容足够",
            "external": False,
            "status": "candidate",
        },
    ]


def test_memory_decay_without_growth_unchanged(tmp_path):
    st = MemoryStore(tmp_path / "memory.db", owner_key="ws1")
    old = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
    st.upsert_fact(
        slot_key="goal.old",
        category="goal",
        statement="过期目标内容足够",
        normalized_value_hash=value_hash("过期目标内容足够"),
        origin="direct",
        status="confirmed",
        fact_id="f_stale",
    )
    with st._connect() as conn:
        conn.execute(
            "UPDATE memory_facts SET last_seen_at = ?, updated_at = ? WHERE id = ?",
            (old, old, "f_stale"),
        )
        conn.commit()
    job = MemoryMaintenanceJob(st, growth=None)
    assert job.run()["changed"] == 1


def test_restore_and_list_panel(client):
    store = client.app.state.container.memory_service.store
    stale = store.upsert_fact(
        slot_key="preference.stale",
        category="preference",
        statement="已淡出记忆内容",
        normalized_value_hash=value_hash("已淡出记忆内容"),
        origin="direct",
        status="stale",
        fact_id="stale1",
    )
    old_seen = "2026-01-01T00:00:00+00:00"
    store.set_last_seen_at("stale1", old_seen, touch_updated=False)
    listed = client.get("/api/memory/facts").json()
    assert [f["id"] for f in listed["stale"]] == [stale["id"]]
    assert stale["id"] not in [f["id"] for f in listed["facts"]]
    ok = client.post("/api/memory/facts/stale1/restore")
    assert ok.status_code == 200
    assert store.get_fact("stale1")["status"] == "confirmed"
    assert store.get_fact("stale1")["last_seen_at"] > old_seen
    bad = client.post(f"/api/memory/facts/{stale['id']}/restore")
    assert bad.status_code == 400
    missing = client.post("/api/memory/facts/no-such/restore")
    assert missing.status_code == 404


def test_growth_route_owner_and_cards_reject(client):
    store = client.app.state.container.memory_service.store
    store.upsert_fact(
        slot_key="preference.route",
        category="preference",
        statement="路由测试记忆内容",
        normalized_value_hash=value_hash("路由测试记忆内容"),
        origin="direct",
        status="confirmed",
        fact_id="route1",
    )
    cards = client.app.state.container.knowledge_cards
    cards.growth.append(
        OWNER_SCOPE,
        "learned",
        [
            {
                "action": "new",
                "card_id": "route1",
                "kind": "preference",
                "statement": "路由测试记忆内容",
                "external": False,
                "status": "confirmed",
            }
        ],
    )
    ok = client.get("/api/cards/growth", params={"scope": "owner"})
    assert ok.status_code == 200
    body = ok.json()
    assert body["scope"] == OWNER_SCOPE
    assert [(e["kind"], e["items"]) for e in body["entries"]] == [
        (
            "learned",
            [
                {
                    "action": "new",
                    "card_id": "route1",
                    "kind": "preference",
                    "statement": "路由测试记忆内容",
                    "external": False,
                    "status": "confirmed",
                }
            ],
        )
    ]
    bad = client.get("/api/cards", params={"scope": "owner"})
    assert bad.status_code == 400
