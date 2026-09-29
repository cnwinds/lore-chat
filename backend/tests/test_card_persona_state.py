from app.engine.memory.card_growth import CardGrowthLog
from app.engine.memory.card_persona_state import CardPersonaState


def test_marks_upsert_and_reject_revision(tmp_path):
    db = tmp_path / "memory.db"
    st = CardPersonaState(db)
    scope = "role:r1"
    st.set_marks(scope, [("c1", "merged", "hash1", "rev1")])
    st.set_marks(scope, [("c2", "reviewed", "hash1", None)])
    marks = st.marks(scope)
    assert marks["c1"]["state"] == "merged"
    assert marks["c2"]["state"] == "reviewed"
    n = st.reject_revision(scope, "rev1")
    assert n == 1
    assert st.marks(scope)["c1"]["state"] == "rejected"
    assert st.reject_revision(scope, "rev1") == 0


def test_proposals_lifecycle(tmp_path):
    st = CardPersonaState(tmp_path / "m.db")
    scope = "role:x"
    prop = st.add_proposal(
        scope,
        target="skill",
        title="T",
        reason="R",
        basis=[{"card_id": "c1", "statement": "s"}],
    )
    listed = st.list_proposals(scope)
    assert listed[0]["status"] == "pending"
    out = st.decide_proposal(scope, prop["id"], "accepted")
    assert out and out["status"] == "accepted"
    assert st.decide_proposal(scope, prop["id"], "dismissed") is None


def test_growth_mark_evolved(tmp_path):
    g = CardGrowthLog(tmp_path / "g.db")
    ts = "2020-01-01T00:00:00+00:00"
    g.mark_evolved("role:r", ts)
    assert g.scope_state("role:r")["last_evolved_at"] == ts


def test_purge(tmp_path):
    st = CardPersonaState(tmp_path / "m.db")
    scope = "role:p"
    st.set_marks(scope, [("c1", "merged", "h", None)])
    st.add_proposal(scope, target="doc", title="t", reason="r", basis=[])
    assert st.purge(scope) >= 2
    assert st.marks(scope) == {}
    assert st.list_proposals(scope) == []
