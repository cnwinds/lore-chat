import json
from datetime import datetime, timedelta, timezone

from app.engine.memory.card_consolidation import (
    CARD_PROFILE,
    LLMCardConsolidator,
    _SYSTEM_PROMPT,
)
from app.engine.memory.cards import CardLens, KnowledgeCards, role_scope
from app.engine.memory.resolver import SlotAction
from app.engine.memory.service import MemoryService
from app.engine.memory.store import MemoryStore
from app.engine.roles import RoleStore
from app.storage.repo import KnowledgeRepo
from tests.helpers import make_writer


class FakeLLM:
    def __init__(self, payload: str | dict):
        self.payload = payload
        self.last_messages = None

    def chat(self, messages, **_kwargs):
        self.last_messages = messages
        if isinstance(self.payload, str):
            return self.payload
        return json.dumps(self.payload, ensure_ascii=False)


def _setup(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    writer = make_writer(repo, tmp_path)
    owner = MemoryService(
        MemoryStore(tmp_path / "memory.db", owner_key="ws1"), repo, knowledge_writer=writer
    )
    roles = RoleStore(tmp_path / "roles")
    role = roles.create(name="整理角色", system_prompt="领域助手人设")
    scope = role_scope(role["id"])
    cards = KnowledgeCards(tmp_path / "memory.db", owner=owner, roles=roles)
    lens = CardLens(scope, "direct", role["name"], role.get("system_prompt") or "")
    return cards, roles, scope, lens


def _seed(
    st: MemoryStore,
    *,
    fact_id: str,
    statement: str,
    vhash: str | None = None,
    origin="direct",
    status="confirmed",
    slot_key=None,
    kind="lesson",
):
    st.upsert_fact(
        slot_key=slot_key or f"{kind}.topic_{fact_id}",
        category=kind,
        statement=statement,
        normalized_value_hash=vhash or f"h-{fact_id}",
        origin=origin,
        status=status,
        fact_id=fact_id,
    )


def _ops(items: list[dict]):
    return {"ops": items}


def _short_map(st: MemoryStore) -> dict[str, dict]:
    facts = st.list_confirmed() + st.list_candidates()
    facts.sort(key=lambda f: f.get("updated_at") or "", reverse=True)
    return {f"c{i + 1}": f for i, f in enumerate(facts)}


def _short_ids(st: MemoryStore, *fact_ids: str) -> list[str]:
    short = _short_map(st)
    inv = {v["id"]: k for k, v in short.items()}
    return [inv[fid] for fid in fact_ids]


def test_prompt_assembled_verbatim(tmp_path):
    cards, _, scope, lens = _setup(tmp_path)
    st = cards.store(scope)
    _seed(st, fact_id="c1", statement="卡一内容足够长", kind="lesson")
    _seed(st, fact_id="c2", statement="卡二内容足够长", vhash="hc", kind="lesson")
    llm = FakeLLM(_ops([]))
    cards.consolidator = LLMCardConsolidator(llm, cards)
    cards.consolidator.run(scope, lens)
    assert llm.last_messages[0]["content"] == _SYSTEM_PROMPT
    user = llm.last_messages[1]["content"]
    assert "c1｜lesson｜主人来源｜已确认" in user
    assert "整理角色" in user


def test_merge_two_owner_cards(tmp_path):
    cards, _, scope, lens = _setup(tmp_path)
    st = cards.store(scope)
    _seed(st, fact_id="a", statement="经验甲内容", kind="lesson")
    _seed(st, fact_id="b", statement="经验乙内容", vhash="hb", kind="lesson")
    st.add_session_evidence("a", "s1")
    st.add_session_evidence("b", "s2")
    c_a, c_b = _short_ids(st, "a", "b")
    max_seen = max(
        st.get_fact("a")["last_seen_at"],
        st.get_fact("b")["last_seen_at"],
    )
    llm = FakeLLM(
        _ops(
            [
                {
                    "op": "merge",
                    "ids": [c_a, c_b],
                    "kind": "lesson",
                    "statement": "合并后的经验正文",
                }
            ]
        )
    )
    cards.consolidator = LLMCardConsolidator(llm, cards)
    result = cards.consolidator.run(scope, lens)
    assert result["ops_applied"] == 1
    kept = st.get_fact("a")
    assert kept["statement"] == "合并后的经验正文"
    assert st.get_fact("b")["status"] == "superseded"
    assert st.count_distinct_conversation_evidence("a") == 2
    assert kept["last_seen_at"] == max_seen
    growth = cards.growth.list(scope)[0]["items"][0]
    assert growth["action"] == "merged"


def test_g5_reject_mixed_merge(tmp_path):
    cards, _, scope, lens = _setup(tmp_path)
    st = cards.store(scope)
    _seed(st, fact_id="e1", statement="外部声称内容", origin="external", kind="audience")
    _seed(st, fact_id="d1", statement="主人来源内容", vhash="hd", kind="lesson")
    llm = FakeLLM(
        _ops(
            [
                {
                    "op": "merge",
                    "ids": ["c1", "c2"],
                    "statement": "不应合并",
                }
            ]
        )
    )
    cards.consolidator = LLMCardConsolidator(llm, cards)
    assert cards.consolidator.run(scope, lens)["ops_applied"] == 0


def test_supersede_external_beats_owner_rejected(tmp_path):
    cards, _, scope, lens = _setup(tmp_path)
    st = cards.store(scope)
    _seed(st, fact_id="o", statement="主人旧说法", kind="lesson")
    _seed(st, fact_id="x", statement="外部新说法", vhash="hx", origin="external", kind="audience")
    llm = FakeLLM(_ops([{"op": "supersede", "ids": ["c2", "c1"]}]))
    cards.consolidator = LLMCardConsolidator(llm, cards)
    assert cards.consolidator.run(scope, lens)["ops_applied"] == 0


def test_supersede_external_winner_no_evidence_move(tmp_path):
    cards, _, scope, lens = _setup(tmp_path)
    st = cards.store(scope)
    _seed(
        st,
        fact_id="w",
        statement="外部较新",
        origin="external",
        status="candidate",
        kind="audience",
    )
    _seed(
        st,
        fact_id="l",
        statement="外部较旧",
        vhash="hl",
        origin="external",
        status="candidate",
        kind="audience",
    )
    st.add_session_evidence("w", "c1")
    st.add_session_evidence("l", "c1")
    st.add_session_evidence("l", "c2")
    with st._connect() as conn:
        conn.execute(
            "UPDATE memory_facts SET last_seen_at = ? WHERE id = ?",
            ("2026-01-02T00:00:00+00:00", "w"),
        )
        conn.execute(
            "UPDATE memory_facts SET last_seen_at = ? WHERE id = ?",
            ("2026-01-01T00:00:00+00:00", "l"),
        )
        conn.commit()
    llm = FakeLLM(_ops([{"op": "supersede", "ids": ["c2", "c1"]}]))
    cards.consolidator = LLMCardConsolidator(llm, cards)
    assert cards.consolidator.run(scope, lens)["ops_applied"] == 1
    assert st.get_fact("w")["status"] == "candidate"
    assert st.count_distinct_conversation_evidence("w") == 1
    assert st.has_value_tombstone(st.get_fact("l")["normalized_value_hash"])


def test_g4_manual_not_in_merge(tmp_path):
    cards, _, scope, lens = _setup(tmp_path)
    st = cards.store(scope)
    _seed(st, fact_id="m", statement="主人亲定内容", origin="manual", kind="lesson")
    _seed(st, fact_id="d", statement="普通内容", vhash="hd", kind="lesson")
    llm = FakeLLM(
        _ops(
            [
                {
                    "op": "merge",
                    "ids": ["c1", "c2"],
                    "statement": "试图合并亲定",
                }
            ]
        )
    )
    cards.consolidator = LLMCardConsolidator(llm, cards)
    assert cards.consolidator.run(scope, lens)["ops_applied"] == 0


def test_g4_manual_as_qualify_reference_ok(tmp_path):
    cards, _, scope, lens = _setup(tmp_path)
    st = cards.store(scope)
    _seed(st, fact_id="m", statement="亲定对照", origin="manual", kind="lesson")
    _seed(st, fact_id="d", statement="需补条件内容", vhash="hd", kind="lesson")
    c_m, c_d = _short_ids(st, "m", "d")
    llm = FakeLLM(
        _ops(
            [
                {
                    "op": "qualify",
                    "ids": [c_m, c_d],
                    "rewrite": {c_d: "讲新概念时要详细说明"},
                }
            ]
        )
    )
    cards.consolidator = LLMCardConsolidator(llm, cards)
    assert cards.consolidator.run(scope, lens)["ops_applied"] == 1


def test_g6_external_abstract_practice_rejected(tmp_path):
    cards, _, scope, lens = _setup(tmp_path)
    st = cards.store(scope)
    _seed(st, fact_id="e1", statement="外部一", origin="external", kind="audience")
    _seed(st, fact_id="e2", statement="外部二", vhash="he2", origin="external", kind="domain")
    llm = FakeLLM(
        _ops(
            [
                {
                    "op": "abstract",
                    "ids": ["c1", "c2"],
                    "kind": "practice",
                    "slot_key": "practice.ext",
                    "statement": "不应出现 practice",
                }
            ]
        )
    )
    cards.consolidator = LLMCardConsolidator(llm, cards)
    assert cards.consolidator.run(scope, lens)["ops_applied"] == 0


def test_g2_duplicate_id_in_ops(tmp_path):
    cards, _, scope, lens = _setup(tmp_path)
    st = cards.store(scope)
    _seed(st, fact_id="a", statement="卡A内容", kind="lesson")
    _seed(st, fact_id="b", statement="卡B内容", vhash="hb", kind="lesson")
    llm = FakeLLM(
        _ops(
            [
                {"op": "merge", "ids": ["c1", "c2"], "statement": "第一次合并正文"},
                {"op": "qualify", "ids": ["c1", "c2"], "rewrite": {"c1": "第二次改写"}},
            ]
        )
    )
    cards.consolidator = LLMCardConsolidator(llm, cards)
    result = cards.consolidator.run(scope, lens)
    assert result["ops_applied"] == 1


def test_g7_secret_rejected(tmp_path):
    cards, _, scope, lens = _setup(tmp_path)
    st = cards.store(scope)
    _seed(st, fact_id="a", statement="卡A内容", kind="lesson")
    _seed(st, fact_id="b", statement="卡B内容", vhash="hb", kind="lesson")
    llm = FakeLLM(
        _ops(
            [
                {
                    "op": "merge",
                    "ids": ["c1", "c2"],
                    "statement": "sk-1234567890123456789012345678901234567890",
                }
            ]
        )
    )
    cards.consolidator = LLMCardConsolidator(llm, cards)
    assert cards.consolidator.run(scope, lens)["ops_applied"] == 0


def test_g7_tombstone_rejected(tmp_path):
    cards, _, scope, lens = _setup(tmp_path)
    st = cards.store(scope)
    _seed(st, fact_id="a", statement="卡A内容", kind="lesson")
    _seed(st, fact_id="b", statement="卡B内容", vhash="hb", kind="lesson")
    from app.engine.memory.normalize import value_hash

    blocked_stmt = "被墓碑挡住的合并句内容"
    st.block_value(
        slot_key="lesson.x",
        normalized_value_hash=value_hash(blocked_stmt),
        reason="user_forget",
    )
    llm = FakeLLM(
        _ops(
            [
                {
                    "op": "merge",
                    "ids": ["c1", "c2"],
                    "statement": blocked_stmt,
                }
            ]
        )
    )
    cards.consolidator = LLMCardConsolidator(llm, cards)
    assert cards.consolidator.run(scope, lens)["ops_applied"] == 0


def test_abstract_last_seen_from_originals_not_now(tmp_path):
    cards, _, scope, lens = _setup(tmp_path)
    st = cards.store(scope)
    old_a = "2020-01-01T00:00:00+00:00"
    old_b = "2021-06-01T00:00:00+00:00"
    _seed(st, fact_id="a", statement="具体经验甲内容", kind="practice")
    _seed(st, fact_id="b", statement="具体经验乙内容", vhash="hb", kind="practice")
    with st._connect() as conn:
        conn.execute(
            "UPDATE memory_facts SET last_seen_at = ?, updated_at = ? WHERE id = ?",
            (old_a, old_a, "a"),
        )
        conn.execute(
            "UPDATE memory_facts SET last_seen_at = ?, updated_at = ? WHERE id = ?",
            (old_b, old_b, "b"),
        )
        conn.commit()
    c_a, c_b = _short_ids(st, "a", "b")
    llm = FakeLLM(
        _ops(
            [
                {
                    "op": "abstract",
                    "ids": [c_a, c_b],
                    "kind": "practice",
                    "slot_key": "practice.shared",
                    "statement": "抽象出的共用做法原则",
                }
            ]
        )
    )
    cards.consolidator = LLMCardConsolidator(llm, cards)
    assert cards.consolidator.run(scope, lens)["ops_applied"] == 1
    new_id = cards.growth.list(scope)[0]["items"][0]["card_id"]
    assert st.get_fact(new_id)["last_seen_at"] == old_b


def test_qualify_rewritten_keeps_last_seen_reference_unchanged(tmp_path):
    cards, _, scope, lens = _setup(tmp_path)
    st = cards.store(scope)
    old_a = "2020-03-01T00:00:00+00:00"
    old_b = "2022-08-01T00:00:00+00:00"
    _seed(st, fact_id="a", statement="讲新概念时要详细", kind="practice")
    _seed(st, fact_id="b", statement="做决策时要直给", vhash="hb", kind="practice")
    with st._connect() as conn:
        conn.execute(
            "UPDATE memory_facts SET last_seen_at = ?, updated_at = ? WHERE id = ?",
            (old_a, old_a, "a"),
        )
        conn.execute(
            "UPDATE memory_facts SET last_seen_at = ?, updated_at = ? WHERE id = ?",
            (old_b, old_b, "b"),
        )
        conn.commit()
    c_a, c_b = _short_ids(st, "a", "b")
    llm = FakeLLM(
        _ops(
            [
                {
                    "op": "qualify",
                    "ids": [c_a, c_b],
                    "rewrite": {c_a: "讲新概念时要详细说明背景"},
                }
            ]
        )
    )
    cards.consolidator = LLMCardConsolidator(llm, cards)
    assert cards.consolidator.run(scope, lens)["ops_applied"] == 1
    assert st.get_fact("a")["last_seen_at"] == old_a
    assert st.get_fact("b")["last_seen_at"] == old_b


def test_g8_second_op_collides_with_first_result(tmp_path):
    cards, _, scope, lens = _setup(tmp_path)
    st = cards.store(scope)
    _seed(st, fact_id="a", statement="卡A内容", kind="lesson")
    _seed(st, fact_id="b", statement="卡B内容", vhash="hb", kind="lesson")
    _seed(st, fact_id="c", statement="卡C内容", vhash="hc", kind="lesson")
    _seed(st, fact_id="d", statement="卡D内容", vhash="hd", kind="lesson")
    c_a, c_b, c_c, c_d = _short_ids(st, "a", "b", "c", "d")
    shared = "两条合并共用结果正文"
    llm = FakeLLM(
        _ops(
            [
                {"op": "merge", "ids": [c_a, c_b], "statement": shared},
                {"op": "merge", "ids": [c_c, c_d], "statement": shared},
            ]
        )
    )
    cards.consolidator = LLMCardConsolidator(llm, cards)
    result = cards.consolidator.run(scope, lens)
    assert result["ops_applied"] == 1
    assert len(result["dropped"]) == 1
    assert result["dropped"][0][1] == "G7_statement"


def test_g8_duplicate_alive_value(tmp_path):
    cards, _, scope, lens = _setup(tmp_path)
    st = cards.store(scope)
    _seed(st, fact_id="a", statement="卡A内容", kind="lesson")
    _seed(st, fact_id="b", statement="卡B内容", vhash="hb", kind="lesson")
    from app.engine.memory.normalize import value_hash

    dup_stmt = "已有存活"
    _seed(st, fact_id="c", statement=dup_stmt, vhash=value_hash(dup_stmt), kind="lesson")
    c_a, c_b = _short_ids(st, "a", "b")
    llm = FakeLLM(
        _ops(
            [
                {
                    "op": "merge",
                    "ids": [c_a, c_b],
                    "statement": dup_stmt,
                }
            ]
        )
    )
    cards.consolidator = LLMCardConsolidator(llm, cards)
    assert cards.consolidator.run(scope, lens)["ops_applied"] == 0


def test_g9_stale_snapshot_dropped(tmp_path):
    cards, _, scope, lens = _setup(tmp_path)
    st = cards.store(scope)
    _seed(st, fact_id="a", statement="卡A内容", kind="lesson")
    _seed(st, fact_id="b", statement="卡B内容", vhash="hb", kind="lesson")

    class RaceLLM(FakeLLM):
        def chat(self, messages, **_kwargs):
            st.update_fact_content(
                "a",
                statement="摄入期间已改",
                normalized_value_hash="ha2",
            )
            return super().chat(messages, **_kwargs)

    llm = RaceLLM(
        _ops(
            [
                {
                    "op": "merge",
                    "ids": ["c1", "c2"],
                    "statement": "合并应被丢弃",
                }
            ]
        )
    )
    cards.consolidator = LLMCardConsolidator(llm, cards)
    assert cards.consolidator.run(scope, lens)["ops_applied"] == 0


def test_abstract_three_confirmed(tmp_path):
    cards, _, scope, lens = _setup(tmp_path)
    st = cards.store(scope)
    for i in range(3):
        _seed(
            st,
            fact_id=f"a{i}",
            statement=f"具体经验{i}内容",
            vhash=f"h{i}",
            kind="practice",
        )
        st.add_session_evidence(f"a{i}", f"s{i}")
    llm = FakeLLM(
        _ops(
            [
                {
                    "op": "abstract",
                    "ids": ["c1", "c2", "c3"],
                    "kind": "practice",
                    "slot_key": "practice.shared_rule",
                    "statement": "抽象出的共用做法原则",
                }
            ]
        )
    )
    cards.consolidator = LLMCardConsolidator(llm, cards)
    assert cards.consolidator.run(scope, lens)["ops_applied"] == 1
    new_items = cards.growth.list(scope)[0]["items"]
    new_id = new_items[0]["card_id"]
    assert st.get_fact(new_id)["status"] == "confirmed"
    for i in range(3):
        old = st.get_fact(f"a{i}")
        assert old["status"] == "superseded"
        assert old["supersedes_id"] == new_id
    assert st.count_distinct_conversation_evidence(new_id) == 3


def test_g11_slot_conflict_fallback(tmp_path):
    cards, _, scope, lens = _setup(tmp_path)
    st = cards.store(scope)
    _seed(
        st,
        fact_id="exist",
        statement="占用槽",
        slot_key="practice.shared_rule",
        kind="practice",
    )
    _seed(st, fact_id="a", statement="卡A内容", vhash="ha", kind="practice")
    _seed(st, fact_id="b", statement="卡B内容", vhash="hb", kind="practice")
    c_a, c_b = _short_ids(st, "a", "b")
    llm = FakeLLM(
        _ops(
            [
                {
                    "op": "abstract",
                    "ids": [c_a, c_b],
                    "kind": "practice",
                    "slot_key": "practice.shared_rule",
                    "statement": "另一抽象原则内容",
                }
            ]
        )
    )
    cards.consolidator = LLMCardConsolidator(llm, cards)
    assert cards.consolidator.run(scope, lens)["ops_applied"] == 1
    new_id = cards.growth.list(scope)[0]["items"][0]["card_id"]
    assert ".topic_" in st.get_fact(new_id)["slot_key"]


def test_qualify_two_cards(tmp_path):
    cards, _, scope, lens = _setup(tmp_path)
    st = cards.store(scope)
    _seed(st, fact_id="a", statement="讲新概念时要详细", kind="practice")
    _seed(st, fact_id="b", statement="做决策时要直给", vhash="hb", kind="practice")
    llm = FakeLLM(
        _ops(
            [
                {
                    "op": "qualify",
                    "ids": ["c1", "c2"],
                    "rewrite": {
                        "c1": "讲新概念时要详细说明背景",
                        "c2": "做决策时要直给结论",
                    },
                }
            ]
        )
    )
    cards.consolidator = LLMCardConsolidator(llm, cards)
    assert cards.consolidator.run(scope, lens)["ops_applied"] == 1
    items = cards.growth.list(scope)[0]["items"]
    assert len(items) == 2
    assert all(it["action"] == "qualified" for it in items)
    assert all("previous" in it for it in items)


def test_maintain_second_run_same_injected_now_skips_consolidate(tmp_path):
    cards, _, scope, _ = _setup(tmp_path)
    st = cards.store(scope)
    injected = datetime(2027, 6, 1, tzinfo=timezone.utc)
    ts = injected.isoformat()
    _seed(st, fact_id="a", statement="卡A内容", kind="lesson")
    _seed(st, fact_id="b", statement="卡B内容", vhash="hb", kind="lesson")
    with st._connect() as conn:
        for fid in ("a", "b"):
            conn.execute(
                "UPDATE memory_facts SET last_seen_at = ?, updated_at = ? WHERE id = ?",
                (ts, ts, fid),
            )
        conn.commit()
    llm = FakeLLM(_ops([]))
    cards.consolidator = LLMCardConsolidator(llm, cards)
    assert cards.maintain(now=injected)["consolidated_scopes"] == 1

    class FailLLM:
        def chat(self, *_a, **_k):
            raise RuntimeError("should not call")

    cards.consolidator = LLMCardConsolidator(FailLLM(), cards)
    assert cards.maintain(now=injected)["consolidated_scopes"] == 0
    assert cards.maintain(now=injected + timedelta(hours=1))["consolidated_scopes"] == 0


def test_maintain_no_llm_without_changes(tmp_path):
    cards, _, scope, lens = _setup(tmp_path)
    st = cards.store(scope)
    _seed(st, fact_id="a", statement="卡A内容", kind="lesson")
    _seed(st, fact_id="b", statement="卡B内容", vhash="hb", kind="lesson")
    cards.growth.mark_consolidated(scope, datetime.now(timezone.utc).isoformat())

    class FailLLM:
        def chat(self, *_a, **_k):
            raise RuntimeError("should not call")

    cards.consolidator = LLMCardConsolidator(FailLLM(), cards)
    assert cards.maintain(now=datetime.now(timezone.utc))["consolidated_scopes"] == 0


def test_maintain_parse_failure_no_mark(tmp_path):
    cards, _, scope, _ = _setup(tmp_path)
    st = cards.store(scope)
    _seed(st, fact_id="a", statement="卡A内容", kind="lesson")
    _seed(st, fact_id="b", statement="卡B内容", vhash="hb", kind="lesson")

    class GarbageLLM:
        def chat(self, *_a, **_k):
            return "not json at all"

    cards.consolidator = LLMCardConsolidator(GarbageLLM(), cards)
    cards.maintain(now=datetime.now(timezone.utc))
    assert cards.growth.scope_state(scope)["last_consolidated_at"] is None


def test_maintain_llm_exception_no_mark(tmp_path):
    cards, _, scope, _ = _setup(tmp_path)
    st = cards.store(scope)
    _seed(st, fact_id="a", statement="卡A内容", kind="lesson")
    _seed(st, fact_id="b", statement="卡B内容", vhash="hb", kind="lesson")

    class FailLLM:
        def chat(self, *_a, **_k):
            raise RuntimeError("boom")

    cards.consolidator = LLMCardConsolidator(FailLLM(), cards)
    cards.maintain(now=datetime.now(timezone.utc))
    assert cards.growth.scope_state(scope)["last_consolidated_at"] is None


def test_maintain_consolidate_limit_three_scopes(tmp_path):
    cards, roles, _, _ = _setup(tmp_path)
    scopes = []
    for i in range(5):
        role = roles.create(name=f"R{i}", system_prompt="x")
        scope = role_scope(role["id"])
        scopes.append(scope)
        st = cards.store(scope)
        _seed(st, fact_id=f"a{i}", statement=f"A{i}内容", kind="lesson")
        _seed(st, fact_id=f"b{i}", statement=f"B{i}内容", vhash=f"hb{i}", kind="lesson")

    llm = FakeLLM(_ops([]))
    cards.consolidator = LLMCardConsolidator(llm, cards)
    result = cards.maintain(now=datetime.now(timezone.utc), max_consolidations=3)
    assert result["consolidated_scopes"] == 3


def test_external_noop_promotion_three_sessions(tmp_path):
    cards, _, scope, _ = _setup(tmp_path)
    st = cards.store(scope)
    from app.engine.memory.normalize import value_hash

    stmt = "有来访者称套餐不含上门服务"
    slot = f"audience.topic_{value_hash(stmt)[:12]}"
    st.upsert_fact(
        slot_key=slot,
        category="audience",
        statement=stmt,
        normalized_value_hash="hq",
        origin="external",
        status="candidate",
        fact_id="aud",
    )
    for cid in ["s1", "s2", "s3"]:
        cards.learn(
            scope,
            [
                SlotAction(
                    action="noop",
                    statement=stmt,
                    category="audience",
                    origin="external",
                    slot_hint=slot,
                )
            ],
            conversation_id=cid,
        )
    assert st.get_fact("aud")["status"] == "confirmed"
    promoted = [
        it
        for e in cards.growth.list(scope)
        for it in e["items"]
        if it.get("action") == "promoted"
    ]
    assert promoted


def test_card_profile_system_prompt_unchanged():
    assert CARD_PROFILE.system_prompt == _SYSTEM_PROMPT
