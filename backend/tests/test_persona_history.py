import pytest

from app.engine.memory.cards import role_scope
from app.engine.memory.normalize import value_hash
from app.engine.memory.persona_history import (
    PersonaHistory,
    PersonaRollbackError,
    revision_can_rollback,
)
from tests.test_knowledge_cards import _cards


def _history(tmp_path):
    cards, roles, _ = _cards(tmp_path)
    return PersonaHistory(roles, cards), roles, cards


def _seed(cards, scope, cid="c1", stmt="卡"):
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


def test_list_previous_body_and_reasons(tmp_path):
    hist, roles, _ = _history(tmp_path)
    role = roles.create(name="R", system_prompt="v1")
    roles.update(role["id"], system_prompt="v2")
    rev = roles.apply_persona_evolution(
        "role",
        role["id"],
        expected_body="v2",
        new_body="v3",
        meta={
            "ops": [
                {
                    "op": "replace",
                    "find": "v2",
                    "text": "v3",
                    "reason": "因为卡",
                    "basis": [{"ref": "c1", "card_id": "c1", "statement": "卡正文"}],
                }
            ]
        },
    )
    assert rev
    scope = role_scope(role["id"])
    rows = hist.list(scope, limit=5)
    evo = next(r for r in rows if r["id"] == rev["id"])
    assert evo["previous_body"] == "v2"
    assert evo["reasons"][0]["before"] == "v2"
    assert evo["reasons"][0]["after"] == "v3"
    assert evo["reasons"][0]["basis"] == ["卡正文"]


def test_list_limit_two_previous_body_chain(tmp_path):
    hist, roles, _ = _history(tmp_path)
    role = roles.create(name="R", system_prompt="v1")
    roles.update(role["id"], system_prompt="v2")
    roles.apply_persona_evolution(
        "role", role["id"], expected_body="v2", new_body="v3", meta={}
    )
    scope = role_scope(role["id"])
    rows = hist.list(scope, limit=2)
    assert len(rows) == 2
    assert rows[1]["previous_body"] == "v1"


def test_can_rollback_rules(tmp_path):
    hist, roles, _ = _history(tmp_path)
    role = roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    roles.update(role["id"], system_prompt="首版人设")
    rows = hist.list(scope, limit=5)
    manual = next(r for r in rows if r["source"] == "manual")
    assert manual["can_rollback"] is True
    assert manual["previous_body"] == ""

    role2 = roles.create(name="R2", system_prompt="seed")
    scope2 = role_scope(role2["id"])
    baseline_rows = hist.list(scope2, limit=10)
    create_rev = next(r for r in baseline_rows if r["source"] == "create")
    assert create_rev["can_rollback"] is False
    if any(r["source"] == "baseline" for r in baseline_rows):
        bl = next(r for r in baseline_rows if r["source"] == "baseline")
        assert bl["can_rollback"] is False

    rev = revision_can_rollback({"source": "evolution", "rolled_back_by": "x"}, has_earlier_revision=True)
    assert rev is False


def test_rollback_merge_and_marks(tmp_path):
    hist, roles, cards = _history(tmp_path)
    role = roles.create(name="R", system_prompt="base")
    scope = role_scope(role["id"])
    roles.update(role["id"], system_prompt="base\nextra")
    rev = roles.apply_persona_evolution(
        "role",
        role["id"],
        expected_body="base\nextra",
        new_body="base\nextra\nfrom card",
        meta={"ops": []},
    )
    stmt = "卡句"
    _seed(cards, scope, stmt=stmt)
    cards.persona_state.set_marks(
        scope,
        [("c1", "merged", value_hash(stmt), rev["id"])],
    )
    out = hist.rollback(scope, rev["id"])
    assert out["ok"] is True
    assert out["body"] == "base\nextra"
    assert out["revision"]["previous_body"] == "base\nextra\nfrom card"
    assert cards.persona_state.marks(scope)["c1"]["state"] == "rejected"


def test_rollback_older_revision_preserves_later_edit(tmp_path):
    hist, roles, _ = _history(tmp_path)
    role = roles.create(name="R", system_prompt="AAAA\nBBBB")
    scope = role_scope(role["id"])
    mid = roles.apply_persona_evolution(
        "role",
        role["id"],
        expected_body="AAAA\nBBBB",
        new_body="AAAA-evo\nBBBB",
        meta={},
    )
    roles.update(role["id"], system_prompt="AAAA-evo\nBBBB-later")
    out = hist.rollback(scope, mid["id"])
    assert out["body"] == "AAAA\nBBBB-later"


def test_rollback_when_change_already_undone(tmp_path):
    hist, roles, _ = _history(tmp_path)
    role = roles.create(name="R", system_prompt="v1")
    scope = role_scope(role["id"])
    roles.update(role["id"], system_prompt="v2")
    evo = roles.apply_persona_evolution(
        "role", role["id"], expected_body="v2", new_body="v3", meta={}
    )
    roles.update(role["id"], system_prompt="v2")
    out = hist.rollback(scope, evo["id"])
    assert out["body"] == "v2"
    assert out["revision"]["source"] == "rollback"
    target = roles.get_persona_revision(evo["id"])
    assert target["rolled_back_by"] == out["revision"]["id"]


def test_rollback_reverts_shape(tmp_path):
    hist, roles, _ = _history(tmp_path)
    role = roles.create(name="R", system_prompt="a")
    scope = role_scope(role["id"])
    roles.update(role["id"], system_prompt="b")
    evo = roles.apply_persona_evolution(
        "role", role["id"], expected_body="b", new_body="c", meta={}
    )
    out = hist.rollback(scope, evo["id"])
    rev = out["revision"]
    assert rev["reverts"]["id"] == evo["id"]
    assert rev["reverts"]["source"] == "evolution"
    assert rev["reverts"]["created_at"] == evo["created_at"]


def test_rollback_conflict(tmp_path):
    hist, roles, _ = _history(tmp_path)
    role = roles.create(name="R", system_prompt="A")
    roles.update(role["id"], system_prompt="AB")
    rev = roles.apply_persona_evolution(
        "role",
        role["id"],
        expected_body="AB",
        new_body="ABX",
        meta={},
    )
    scope = role_scope(role["id"])
    roles.update(role["id"], system_prompt="AC")
    with pytest.raises(PersonaRollbackError) as exc:
        hist.rollback(scope, rev["id"])
    assert exc.value.code == "conflict"
