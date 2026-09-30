"""人设进化器与 maintain 调度（P2 · 任务 B）。"""

import json
from datetime import datetime, timedelta, timezone

from app.engine.memory.cards import CardLens, KnowledgeCards, persona_scope, role_scope
from app.engine.memory.normalize import value_hash
from app.engine.memory.persona_evolution import (
    LLMPersonaEvolver,
    _SYSTEM_PROMPT,
    _USER_TEMPLATE,
)
from app.engine.memory.persona_history import PersonaHistory
from app.engine.memory.service import MemoryService
from app.engine.memory.store import MemoryStore
from app.engine.persona_edits import owner_changes
from app.engine.roles import RoleStore
from app.storage.repo import KnowledgeRepo
from tests.helpers import make_writer


class FakeLLM:
    def __init__(self, payload: str | dict, *, on_chat=None):
        self.payload = payload
        self.on_chat = on_chat
        self.last_messages = None

    def chat(self, messages, **_kwargs):
        self.last_messages = messages
        if self.on_chat:
            self.on_chat()
        if isinstance(self.payload, str):
            return self.payload
        return json.dumps(self.payload, ensure_ascii=False)


def _setup(tmp_path, *, prompt: str = "人设\n第二行"):
    repo = KnowledgeRepo(tmp_path / "knowledge", protected_dirs=("系统",))
    writer = make_writer(repo, tmp_path)
    owner = MemoryService(
        MemoryStore(tmp_path / "memory.db", owner_key="ws1"), repo, knowledge_writer=writer
    )
    roles = RoleStore(tmp_path / "roles")
    role = roles.create(name="进化角色", system_prompt=prompt)
    scope = role_scope(role["id"])
    cards = KnowledgeCards(tmp_path / "memory.db", owner=owner, roles=roles)
    lens = CardLens(scope, "direct", role["name"], role.get("system_prompt") or "")
    evolver = LLMPersonaEvolver(llm=FakeLLM({"edits": [], "proposals": []}), cards=cards)
    cards.evolver = evolver
    return cards, roles, scope, lens, evolver


def _seed(
    st: MemoryStore,
    *,
    fact_id: str,
    statement: str = "卡正文足够长",
    origin="direct",
    status="confirmed",
    kind="practice",
):
    st.upsert_fact(
        slot_key=f"{kind}.topic_{fact_id}",
        category=kind,
        statement=statement,
        normalized_value_hash=f"h-{fact_id}",
        origin=origin,
        status=status,
        fact_id=fact_id,
    )


def _eligible_card(st, cards, scope, fact_id="c1", **kw):
    _seed(st, fact_id=fact_id, **kw)
    st.add_session_evidence(fact_id, "s1")
    st.add_session_evidence(fact_id, "s2")


def _eligible_cards_newest_first_ref(st, cards, scope, specs: list[dict]):
    """按 specs 顺序创建；最后一张 updated_at 最新，进化器里为 c1。"""
    for spec in specs:
        fid = spec.pop("fact_id")
        _eligible_card(st, cards, scope, fid, **spec)


def test_should_run_thresholds(tmp_path):
    cards, _, scope, _, evolver = _setup(tmp_path)
    st = cards.store(scope)
    assert evolver.should_run(scope) is False
    _eligible_card(st, cards, scope, "ok")
    assert evolver.should_run(scope) is True
    _seed(st, fact_id="ext", origin="external")
    st.add_session_evidence("ext", "a")
    st.add_session_evidence("ext", "b")
    _seed(st, fact_id="cand", status="candidate")
    _seed(st, fact_id="one", statement="一段")
    st.add_session_evidence("one", "only")
    _seed(st, fact_id="manual", origin="manual", statement="亲定")
    cards.persona_state.set_marks(
        scope,
        [
            (
                "ok",
                "merged",
                value_hash("卡正文足够长"),
                "r1",
            )
        ],
    )
    assert evolver.should_run(scope) is True
    cards.persona_state.set_marks(
        scope,
        [
            (
                "manual",
                "reviewed",
                value_hash("亲定"),
                None,
            )
        ],
    )
    assert evolver.should_run(scope) is False


def test_persona_scope_external_only_does_not_run(tmp_path):
    cards, roles, _, _, evolver = _setup(tmp_path)
    persona = roles.create_persona(name="通道人设", system_prompt="p")
    pscope = persona_scope(persona["id"])
    st = cards.store(pscope)
    _seed(st, fact_id="ext", origin="external", status="confirmed")
    st.add_session_evidence("ext", "s1")
    st.add_session_evidence("ext", "s2")
    st.add_session_evidence("ext", "s3")
    assert evolver.should_run(pscope) is False
    lens = CardLens(pscope, "external", persona["name"], persona["system_prompt"])
    assert evolver.run(pscope, lens) == {"skipped": "no_new_cards"}


def test_persona_scope_evolves_with_manual_card(tmp_path):
    cards, roles, _, _, evolver = _setup(tmp_path, prompt="通道人设\n")
    persona = roles.create_persona(name="通道人设", system_prompt="通道人设\n")
    pid = persona["id"]
    pscope = persona_scope(pid)
    st = cards.store(pscope)
    _seed(st, fact_id="ext", origin="external", statement="外部卡正文", kind="audience")
    st.add_session_evidence("ext", "e1")
    st.add_session_evidence("ext", "e2")
    st.add_session_evidence("ext", "e3")
    _seed(st, fact_id="manual1", origin="manual", statement="亲定做法", kind="practice")
    st.add_session_evidence("manual1", "m1")
    lens = CardLens(pscope, "external", persona["name"], persona["system_prompt"])
    payload = {
        "edits": [
            {
                "op": "insert",
                "after": "",
                "text": "新增段",
                "basis": ["c1"],
                "reason": "并入做法",
            },
            {
                "op": "insert",
                "after": "",
                "text": "不应写入",
                "basis": ["c2"],
                "reason": "外部编号",
            },
        ],
        "proposals": [
            {
                "target": "skill",
                "title": "流程",
                "basis": ["c1"],
                "reason": "应忽略",
            }
        ],
    }
    evolver.llm = FakeLLM(payload)
    result = evolver.run(pscope, lens)
    assert result["edits_applied"] == 1
    assert result["dropped"] == [{"index": 1, "reason": "bad_basis"}]
    assert result["proposals_added"] == 0
    assert cards.persona_state.list_proposals(pscope) == []
    assert roles.get_persona_body("persona", pid) == "通道人设\n新增段\n"
    rev = roles.latest_persona_revision("persona", pid, source="evolution")
    assert rev
    assert rev["source"] == "evolution"
    assert rev["subject_kind"] == "persona"
    meta = rev["meta"]
    assert meta["ops"] == [
        {
            "op": "insert",
            "find": "",
            "after": "",
            "text": "新增段",
            "reason": "并入做法",
            "basis": [
                {
                    "ref": "c1",
                    "card_id": "manual1",
                    "statement": "亲定做法",
                }
            ],
        }
    ]
    marks = cards.persona_state.marks(pscope)
    assert marks["manual1"]["state"] == "merged"
    assert "ext" not in marks
    growth = cards.growth.list(pscope, limit=5)
    prop_items = [it for e in growth if e["kind"] == "proposal" for it in e["items"]]
    assert prop_items == []
    persona_items = [
        it for e in growth if e["kind"] == "persona" for it in e["items"]
    ]
    assert persona_items == [
        {
            "action": "evolved",
            "revision_id": rev["id"],
            "op": "insert",
            "reason": "并入做法",
            "before": "",
            "after": "新增段",
            "basis": ["亲定做法"],
        }
    ]
    user = evolver.llm.last_messages[1]["content"]
    assert "【主人记忆】（编号｜正文）：\n（无）" in user
    assert "- c1｜practice｜主人亲定｜亲定做法" in user
    assert "外部卡正文" not in user


def test_persona_scope_rollback_via_history(tmp_path):
    cards, roles, _, _, evolver = _setup(tmp_path, prompt="通道人设\n")
    persona = roles.create_persona(name="通道人设", system_prompt="通道人设\n")
    pid = persona["id"]
    pscope = persona_scope(pid)
    st = cards.store(pscope)
    _seed(st, fact_id="ext", origin="external", statement="外部卡正文", kind="audience")
    st.add_session_evidence("ext", "e1")
    st.add_session_evidence("ext", "e2")
    st.add_session_evidence("ext", "e3")
    _seed(st, fact_id="manual1", origin="manual", statement="亲定做法", kind="practice")
    st.add_session_evidence("manual1", "m1")
    lens = CardLens(pscope, "external", persona["name"], persona["system_prompt"])
    evolver.llm = FakeLLM(
        {
            "edits": [
                {
                    "op": "insert",
                    "after": "",
                    "text": "新增段",
                    "basis": ["c1"],
                    "reason": "并入做法",
                }
            ],
            "proposals": [],
        }
    )
    r1 = evolver.run(pscope, lens)
    rev_id = r1["revision_id"]
    assert rev_id
    PersonaHistory(roles, cards).rollback(pscope, rev_id)
    assert roles.get_persona_body("persona", pid) == "通道人设\n"
    assert cards.persona_state.marks(pscope)["manual1"]["state"] == "rejected"
    growth = cards.growth.list(pscope, limit=10)
    rolled = [
        it
        for e in growth
        if e["kind"] == "persona"
        for it in e["items"]
        if it.get("action") == "rolled_back"
    ]
    assert len(rolled) == 1
    assert rolled[0]["revision_id"] == rev_id


def test_onboarding_skipped_without_mark_evolved(tmp_path):
    cards, roles, scope, lens, evolver = _setup(tmp_path)
    st = cards.store(scope)
    _eligible_card(st, cards, scope)
    role_id = scope.split(":")[1]
    roles.update(role_id, onboarding_status="active")
    assert evolver.run(scope, lens) == {"skipped": "onboarding"}
    now = datetime.now(timezone.utc)
    assert cards.maintain(now=now)["evolved_scopes"] == 0
    assert cards.growth.scope_state(scope).get("last_evolved_at") is None


def test_run_applies_edits_meta_growth_and_marks(tmp_path):
    cards, roles, scope, lens, evolver = _setup(tmp_path)
    st = cards.store(scope)
    rid = scope.split(":")[1]
    _eligible_cards_newest_first_ref(
        st,
        cards,
        scope,
        [
            {"fact_id": "c2", "statement": "旁卡", "kind": "lesson"},
            {"fact_id": "c1", "statement": "做法一"},
        ],
    )
    cards.owner.store.upsert_fact(
        slot_key="preference.x",
        category="preference",
        statement="主人记忆句",
        normalized_value_hash="hm",
        origin="direct",
        status="confirmed",
        fact_id="mem1",
    )
    payload = {
        "edits": [
            {
                "op": "insert",
                "after": "",
                "text": "新增段",
                "basis": ["c1"],
                "reason": "并入做法",
            },
            {
                "op": "delete",
                "find": "第二行",
                "basis": ["m1"],
                "reason": "与记忆重复",
            },
            {
                "op": "replace",
                "find": "不存在",
                "text": "x",
                "basis": ["c1"],
                "reason": "应丢弃",
            },
        ],
        "proposals": [],
    }
    evolver.llm = FakeLLM(payload)
    result = evolver.run(scope, lens)
    assert result["edits_applied"] == 2
    assert result["dropped"] == [{"index": 2, "reason": "not_found"}]
    assert roles.get_persona_body("role", rid) == "人设\n新增段\n"
    rev = roles.latest_persona_revision("role", rid, source="evolution")
    assert rev
    meta = rev["meta"]
    assert meta["base_revision_id"] is not None
    assert meta["merged_card_ids"] == ["c1"]
    assert meta["ops"] == [
        {
            "op": "insert",
            "find": "",
            "after": "",
            "text": "新增段",
            "reason": "并入做法",
            "basis": [
                {
                    "ref": "c1",
                    "card_id": "c1",
                    "statement": "做法一",
                }
            ],
        },
        {
            "op": "delete",
            "find": "第二行",
            "after": "",
            "text": "",
            "reason": "与记忆重复",
            "basis": [
                {
                    "ref": "m1",
                    "memory_id": "mem1",
                    "statement": "主人记忆句",
                }
            ],
        },
    ]
    marks = cards.persona_state.marks(scope)
    assert marks["c1"]["state"] == "merged"
    assert marks["c2"]["state"] == "reviewed"
    growth = cards.growth.list(scope, limit=5)
    persona_items = [
        it for e in growth if e["kind"] == "persona" for it in e["items"]
    ]
    assert persona_items == [
        {
            "action": "evolved",
            "revision_id": rev["id"],
            "op": "insert",
            "reason": "并入做法",
            "before": "",
            "after": "新增段",
            "basis": ["做法一"],
        },
        {
            "action": "evolved",
            "revision_id": rev["id"],
            "op": "delete",
            "reason": "与记忆重复",
            "before": "第二行",
            "after": "",
            "basis": ["主人记忆句"],
        },
    ]


def test_owner_hand_edit_protected_and_tombstoned(tmp_path):
    cards, roles, scope, lens, evolver = _setup(tmp_path)
    st = cards.store(scope)
    _eligible_card(st, cards, scope)
    rid = scope.split(":")[1]
    before = "人设\n主人改行\n尾"
    roles.update(rid, system_prompt=before)
    prior_evo = roles.apply_persona_evolution(
        "role",
        rid,
        expected_body=before,
        new_body=before + "\n主人不要的段落",
        meta={
            "ops": [
                {
                    "op": "insert",
                    "after": "",
                    "text": "主人不要的段落",
                    "reason": "r",
                    "basis": [],
                }
            ]
        },
    )
    prior_evo_id = prior_evo["id"]
    after_owner = "人设\n主人新行\n尾"
    roles.update(rid, system_prompt=after_owner)
    evolver.llm = FakeLLM(
        {
            "edits": [
                {
                    "op": "replace",
                    "find": "主人新行",
                    "text": "机器改",
                    "basis": ["c1"],
                    "reason": "不应改",
                },
                {
                    "op": "insert",
                    "after": "",
                    "text": "主人不要的段落",
                    "basis": ["c1"],
                    "reason": "主人删过",
                },
            ],
            "proposals": [],
        }
    )
    result = evolver.run(scope, lens)
    assert result["edits_applied"] == 0
    assert result["dropped"] == [
        {"index": 0, "reason": "protected"},
        {"index": 1, "reason": "tombstoned"},
    ]
    assert roles.get_persona_body("role", rid) == after_owner
    latest = roles.latest_persona_revision("role", rid, source="evolution")
    assert latest is not None and latest["id"] == prior_evo_id


def test_rollback_insert_tombstone_isolated(tmp_path):
    cards, roles, scope, lens, evolver = _setup(tmp_path, prompt="keep\n")
    st = cards.store(scope)
    rid = scope.split(":")[1]
    _eligible_card(st, cards, scope, "c1", statement="依据卡")
    e1_text = "不要插入的句子"
    evolver.llm = FakeLLM(
        {
            "edits": [
                {
                    "op": "insert",
                    "after": "",
                    "text": e1_text,
                    "basis": ["c1"],
                    "reason": "e1",
                }
            ],
            "proposals": [],
        }
    )
    r1 = evolver.run(scope, lens)
    e1_id = r1["revision_id"]
    assert e1_id
    assert cards.persona_state.marks(scope)["c1"]["state"] == "merged"
    PersonaHistory(roles, cards).rollback(scope, e1_id)
    assert cards.persona_state.marks(scope)["c1"]["state"] == "rejected"
    assert "c1" not in {f["id"] for f in evolver.eligible_cards(scope)}

    _eligible_card(st, cards, scope, "c2", statement="新卡二")
    evolver.llm = FakeLLM(
        {
            "edits": [
                {
                    "op": "insert",
                    "after": "",
                    "text": "无关尾注",
                    "basis": ["c1"],
                    "reason": "e2",
                }
            ],
            "proposals": [],
        }
    )
    r2 = evolver.run(scope, lens)
    e2_id = r2["revision_id"]
    e2_rev = roles.get_persona_revision(e2_id)
    current = roles.get_persona_body("role", rid)
    oc = owner_changes(e2_rev["body"], current)
    assert oc.added_texts == []
    assert oc.removed_texts == []
    assert oc.protected_spans == []

    _eligible_card(st, cards, scope, "c3", statement="触发三")
    evolver.llm = FakeLLM(
        {
            "edits": [
                {
                    "op": "insert",
                    "after": "",
                    "text": "不要插入的文句",
                    "basis": ["c1"],
                    "reason": "近义",
                }
            ],
            "proposals": [],
        }
    )
    r3 = evolver.run(scope, lens)
    assert r3["dropped"] == [{"index": 0, "reason": "tombstoned"}]


def test_rollback_delete_protected_isolated(tmp_path):
    deleted_line = "删除这一段落"
    cards, roles, scope, lens, evolver = _setup(
        tmp_path, prompt=f"keep\n{deleted_line}\n"
    )
    st = cards.store(scope)
    rid = scope.split(":")[1]
    _eligible_card(st, cards, scope, "c1", statement="依据卡")
    evolver.llm = FakeLLM(
        {
            "edits": [
                {
                    "op": "delete",
                    "find": deleted_line,
                    "basis": ["c1"],
                    "reason": "e1",
                }
            ],
            "proposals": [],
        }
    )
    r1 = evolver.run(scope, lens)
    e1_id = r1["revision_id"]
    PersonaHistory(roles, cards).rollback(scope, e1_id)
    assert deleted_line in roles.get_persona_body("role", rid)

    _eligible_card(st, cards, scope, "c2", statement="新卡二")
    evolver.llm = FakeLLM(
        {
            "edits": [
                {
                    "op": "insert",
                    "after": "",
                    "text": "无关尾注",
                    "basis": ["c1"],
                    "reason": "e2",
                }
            ],
            "proposals": [],
        }
    )
    r2 = evolver.run(scope, lens)
    e2_rev = roles.get_persona_revision(r2["revision_id"])
    current = roles.get_persona_body("role", rid)
    oc = owner_changes(e2_rev["body"], current)
    assert oc.added_texts == [] and oc.removed_texts == [] and oc.protected_spans == []

    _eligible_card(st, cards, scope, "c3", statement="触发三")
    evolver.llm = FakeLLM(
        {
            "edits": [
                {
                    "op": "delete",
                    "find": deleted_line,
                    "basis": ["c1"],
                    "reason": "再删",
                }
            ],
            "proposals": [],
        }
    )
    r3 = evolver.run(scope, lens)
    assert r3["dropped"] == [{"index": 0, "reason": "protected"}]


def test_aborted_when_persona_changed_during_llm(tmp_path):
    cards, roles, scope, lens, evolver = _setup(tmp_path)
    st = cards.store(scope)
    _eligible_card(st, cards, scope)
    rid = scope.split(":")[1]

    def _race():
        roles.update(rid, system_prompt="人设\n被改")

    payload = {
        "edits": [
            {
                "op": "insert",
                "after": "",
                "text": "新",
                "basis": ["c1"],
                "reason": "r",
            }
        ],
        "proposals": [
            {
                "target": "skill",
                "title": "流程",
                "basis": ["c1"],
                "reason": "r",
            }
        ],
    }
    evolver.llm = FakeLLM(payload, on_chat=_race)
    result = evolver.run(scope, lens)
    assert result == {"aborted": "persona_changed"}
    assert roles.latest_persona_revision("role", rid, source="evolution") is None
    assert cards.persona_state.list_proposals(scope) == []


def test_proposal_validation_invalid_first_then_two_valid(tmp_path):
    cards, _, scope, lens, evolver = _setup(tmp_path)
    st = cards.store(scope)
    _eligible_cards_newest_first_ref(
        st,
        cards,
        scope,
        [
            {"fact_id": "ce", "kind": "lesson", "statement": "第三卡"},
            {"fact_id": "cd", "kind": "practice", "statement": "文档卡"},
            {"fact_id": "cc", "kind": "owner_context", "statement": "主在此"},
            {"fact_id": "cb", "kind": "domain", "statement": "域卡"},
            {"fact_id": "ca", "kind": "practice", "statement": "做法卡"},
        ],
    )
    cards.owner.store.upsert_fact(
        slot_key="preference.m",
        category="preference",
        statement="记忆",
        normalized_value_hash="hx",
        origin="direct",
        status="confirmed",
        fact_id="om",
    )
    cards.persona_state.add_proposal(
        scope,
        target="skill",
        title="已有",
        reason="r",
        basis=[{"card_id": "cb", "statement": "域卡"}],
    )
    payload = {
        "edits": [],
        "proposals": [
            {"target": "skill", "title": "x" * 41, "basis": ["c1"], "reason": "长"},
            {"target": "skill", "title": "错种类", "basis": ["c2"], "reason": "域"},
            {"target": "doc", "title": "错doc", "basis": ["c3"], "reason": "主在此"},
            {"target": "skill", "title": "未知", "basis": ["c99"], "reason": "无"},
            {"target": "skill", "title": "记忆", "basis": ["m1"], "reason": "m"},
            {"target": "skill", "title": "空理由", "basis": ["c1"], "reason": "  "},
            {"target": "bogus", "title": "非法", "basis": ["c1"], "reason": "t"},
            {"target": "skill", "title": "相交", "basis": ["c2"], "reason": "已有"},
            {"target": "skill", "title": "合法Skill", "basis": ["c1"], "reason": "好"},
            {"target": "doc", "title": "合法文档", "basis": ["c4"], "reason": "文档"},
            {"target": "skill", "title": "第三条", "basis": ["c5"], "reason": "满额"},
        ],
    }
    evolver.llm = FakeLLM(payload)
    result = evolver.run(scope, lens)
    assert result["proposals_added"] == 2
    pending = [p for p in cards.persona_state.list_proposals(scope) if p["status"] == "pending"]
    titles = {p["title"]: p for p in pending if p["title"] in ("合法Skill", "合法文档")}
    assert len(titles) == 2
    assert titles["合法Skill"]["target"] == "skill"
    assert titles["合法Skill"]["basis"][0]["card_id"] == "ca"
    assert titles["合法文档"]["target"] == "doc"
    assert titles["合法文档"]["basis"][0]["card_id"] == "cd"
    growth = cards.growth.list(scope, limit=3)
    prop_items = [it for e in growth if e["kind"] == "proposal" for it in e["items"]]
    assert len(prop_items) == 2
    by_title = {it["title"]: it for it in prop_items}
    assert by_title["合法Skill"] == {
        "action": "proposed",
        "proposal_id": titles["合法Skill"]["id"],
        "target": "skill",
        "title": "合法Skill",
        "reason": "好",
        "basis": ["做法卡"],
        "status": "pending",
    }
    assert by_title["合法文档"] == {
        "action": "proposed",
        "proposal_id": titles["合法文档"]["id"],
        "target": "doc",
        "title": "合法文档",
        "reason": "文档",
        "basis": ["文档卡"],
        "status": "pending",
    }


def test_proposal_validation_same_card_only_first(tmp_path):
    cards, _, scope, lens, evolver = _setup(tmp_path)
    st = cards.store(scope)
    _eligible_card(st, cards, scope, "c1", kind="practice")
    payload = {
        "edits": [],
        "proposals": [
            {"target": "skill", "title": "第一个", "basis": ["c1"], "reason": "a"},
            {"target": "doc", "title": "第二个", "basis": ["c1"], "reason": "b"},
        ],
    }
    evolver.llm = FakeLLM(payload)
    result = evolver.run(scope, lens)
    assert result["proposals_added"] == 1
    pending = [p for p in cards.persona_state.list_proposals(scope) if p["status"] == "pending"]
    assert len(pending) == 1
    assert pending[0]["title"] == "第一个"
    assert pending[0]["target"] == "skill"


def test_user_message_sections_and_persona_verbatim(tmp_path):
    cards, roles, scope, lens, evolver = _setup(tmp_path, prompt="初始人设\n")
    st = cards.store(scope)
    rid = scope.split(":")[1]
    roles.update(rid, system_prompt="逐字人设\n第二行\n")
    _seed(st, fact_id="c2", statement="亲定卡", origin="manual", kind="practice")
    st.add_session_evidence("c2", "m1")
    _eligible_card(st, cards, scope, "c1", statement="卡片正文", kind="practice")
    cards.owner.store.upsert_fact(
        slot_key="preference.t",
        category="preference",
        statement="主人记忆一行",
        normalized_value_hash="hm2",
        origin="direct",
        status="confirmed",
        fact_id="memx",
    )
    rules = "全局戒律一行"
    evolver.rules_text = lambda: rules
    base_rev = roles.earliest_persona_revision("role", rid)
    current = roles.get_persona_body("role", rid)
    oc = owner_changes(base_rev["body"] if base_rev else "", current)
    evolver.llm = FakeLLM({"edits": [], "proposals": []})
    evolver.run(scope, lens)
    user = evolver.llm.last_messages[1]["content"]
    assert evolver.llm.last_messages[0]["content"] == _SYSTEM_PROMPT
    expected = _USER_TEMPLATE.format(
        subject_name=lens.subject_name,
        current=current,
        owner_lines="\n".join(
            [f"- 加入或改成：「{t.strip()}」" for t in oc.added_texts]
            + [f"- 删掉：「{t.strip()}」" for t in oc.removed_texts]
        )
        or "（无）",
        tombstone_lines="（无）",
        card_lines="\n".join(
            [
                "- c1｜practice｜2 段｜卡片正文",
                "- c2｜practice｜主人亲定｜亲定卡",
            ]
        ),
        memory_lines="- m1｜主人记忆一行",
        proposal_lines="（无）",
        rules=rules,
    )
    assert user == expected
    block = user.split("<<<\n", 1)[1].split("\n>>>", 1)[0]
    assert block == current


def test_maintain_evolve_scheduling(tmp_path):
    cards, roles, scope, lens, evolver = _setup(tmp_path)
    st = cards.store(scope)
    _eligible_card(st, cards, scope, "a")
    role2 = roles.create(name="R2", system_prompt="x")
    scope2 = role_scope(role2["id"])
    st2 = cards.store(scope2)
    _eligible_card(st2, cards, scope2, "b")
    persona = roles.create_persona(name="P", system_prompt="y")
    pscope = persona_scope(persona["id"])
    pst = cards.store(pscope)
    _seed(pst, fact_id="pc", origin="manual", statement="通道亲定")
    pst.add_session_evidence("pc", "ps1")
    scopes = sorted(cards.list_scopes())
    assert {scope, scope2, pscope} <= set(scopes)
    third = sorted([scope, scope2, pscope])[2]
    now = datetime.now(timezone.utc)
    r1 = cards.maintain(now=now)
    assert r1["evolved_scopes"] == 2
    assert cards.growth.scope_state(third).get("last_evolved_at") is None
    r2 = cards.maintain(now=now + timedelta(hours=1))
    assert r2["evolved_scopes"] == 1
    assert cards.growth.scope_state(third).get("last_evolved_at")

    persona3 = roles.create_persona(name="P3", system_prompt="z")
    pscope3 = persona_scope(persona3["id"])
    pst3 = cards.store(pscope3)
    _seed(pst3, fact_id="fresh", origin="manual", statement="新开")
    calls = {"n": 0}

    class CountingEvolver(LLMPersonaEvolver):
        def run(self, s, l):
            calls["n"] += 1
            return {"skipped": "no_new_cards"}

    cards.evolver = CountingEvolver(evolver.llm, cards)
    cards.maintain(now=now + timedelta(hours=50))
    assert calls["n"] == 1

    class BoomEvolver(LLMPersonaEvolver):
        def run(self, s, l):
            raise RuntimeError("boom")

    before_ts = cards.growth.scope_state(scope).get("last_evolved_at")
    cards.evolver = BoomEvolver(evolver.llm, cards)
    _eligible_card(st, cards, scope, "c99")
    boom = cards.maintain(now=now + timedelta(hours=60))
    assert boom["evolved_scopes"] == 0
    assert cards.growth.scope_state(scope).get("last_evolved_at") == before_ts


def test_maintain_consolidation_early_exit_still_evolve(tmp_path):
    cards, _, scope, _, evolver = _setup(tmp_path)
    st = cards.store(scope)
    _eligible_card(st, cards, scope)
    assert len(st.list_confirmed()) == 1
    now = datetime.now(timezone.utc)
    assert cards.maintain(now=now)["evolved_scopes"] == 1
