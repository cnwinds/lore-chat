"""merged 卡注入、提议与 purge（P2 · 任务 A）。"""

from app.engine.memory.cards import role_scope
from app.engine.memory.normalize import value_hash
from tests.test_knowledge_cards import _cards


def _seed(cards, scope, cid="c1", stmt="卡正文"):
    st = cards.store(scope)
    st.upsert_fact(
        slot_key="domain.topic",
        category="domain",
        statement=stmt,
        normalized_value_hash=f"h-{cid}",
        origin="direct",
        status="confirmed",
        fact_id=cid,
    )
    if cards.index is not None:
        with cards.scope_lock(scope):
            cards.index.sync_scope_locked(scope)
    return cid


def test_merged_skips_render_and_turn(tmp_path):
    cards, roles, _ = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="人设")
    scope = role_scope(role["id"])
    stmt = "卡正文"
    cid = _seed(cards, scope, stmt=stmt)
    cards.persona_state.set_marks(
        scope, [(cid, "merged", value_hash(stmt), "rev1")]
    )
    text, ids = cards.render_with_ids(scope)
    assert cid not in ids
    assert stmt not in text
    turn = cards.turn_cards(scope, "卡", exclude_ids=set())
    assert stmt not in turn
    recalled = cards.recall(scope, "卡")
    assert any(r["statement"] == stmt for r in recalled)


def test_merged_invalidate_on_card_edit(tmp_path):
    cards, roles, _ = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="v1")
    scope = role_scope(role["id"])
    stmt = "原始卡文"
    cid = _seed(cards, scope, stmt=stmt)
    cards.persona_state.set_marks(
        scope, [(cid, "merged", value_hash(stmt), "r")]
    )
    assert cid in cards.merged_card_ids(scope)
    cards.edit(scope, cid, "改写后的卡文")
    assert cid not in cards.merged_card_ids(scope)
    _, ids = cards.render_with_ids(scope)
    assert cid in ids


def test_persona_change_does_not_invalidate_merged(tmp_path):
    cards, roles, _ = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="v1")
    scope = role_scope(role["id"])
    stmt = "稳定卡文"
    cid = _seed(cards, scope, stmt=stmt)
    cards.persona_state.set_marks(
        scope, [(cid, "merged", value_hash(stmt), "r")]
    )
    assert cid in cards.merged_card_ids(scope)
    roles.update(role["id"], system_prompt="v2")
    assert cid in cards.merged_card_ids(scope)


def test_proposal_request_text(tmp_path):
    cards, roles, _ = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    _seed(cards, scope, "c1", "旧正文")
    prop = cards.persona_state.add_proposal(
        scope,
        target="skill",
        title="我的Skill",
        reason="理由句",
        basis=[{"card_id": "c1", "statement": "旧正文"}],
    )
    cards.edit(scope, "c1", "新正文")
    out = cards.accept_proposal(scope, prop["id"])
    assert out["ok"] is True
    expected = (
        "请把下面这些经验固化为一个 Skill「我的Skill」：\n\n"
        "- 新正文\n\n"
        "（来自知识卡的升格提议：理由句）"
    )
    assert out["request_text"] == expected
    assert cards.accept_proposal(scope, prop["id"])["ok"] is False


def test_purge_scope_clears_persona_state(tmp_path):
    cards, roles, _ = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    cards.persona_state.set_marks(scope, [("c1", "merged", "h", None)])
    cards.persona_state.add_proposal(
        scope, target="doc", title="t", reason="r", basis=[]
    )
    cards.purge_scope(scope)
    assert cards.persona_state.marks(scope) == {}
    assert cards.persona_state.list_proposals(scope) == []


def test_growth_proposal_status(tmp_path):
    cards, roles, _ = _cards(tmp_path)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    prop = cards.persona_state.add_proposal(
        scope, target="doc", title="t", reason="r", basis=[]
    )
    cards.growth.append(
        scope,
        "proposal",
        [
            {
                "action": "proposed",
                "proposal_id": prop["id"],
                "target": "doc",
                "title": "t",
                "reason": "r",
                "basis": [],
            }
        ],
    )
    cards.persona_state.decide_proposal(scope, prop["id"], "dismissed")
    entries = cards.growth_entries(scope)
    item = entries[0]["items"][0]
    assert item["status"] == "dismissed"
