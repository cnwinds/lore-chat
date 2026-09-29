"""人设历史与提议 HTTP（P2 · 任务 A）。"""

from app.engine.memory.cards import role_scope


def test_persona_revisions_and_rollback_routes(client):
    role = client.app.state.container.roles.create(name="R", system_prompt="a")
    scope = role_scope(role["id"])
    client.app.state.container.roles.update(role["id"], system_prompt="b")
    rev = client.app.state.container.roles.apply_persona_evolution(
        "role",
        role["id"],
        expected_body="b",
        new_body="c",
        meta={},
    )
    listed = client.get("/api/cards/persona/revisions", params={"scope": scope})
    assert listed.status_code == 200
    assert len(listed.json()["revisions"]) >= 1
    rb = client.post(
        f"/api/cards/persona/revisions/{rev['id']}/rollback",
        params={"scope": scope},
    )
    assert rb.status_code == 200
    assert rb.json()["body"] == "b"
    assert rb.json()["revision"]["previous_body"] == "c"


def test_rollback_route_409_conflict(client):
    role = client.app.state.container.roles.create(name="R", system_prompt="A")
    scope = role_scope(role["id"])
    roles = client.app.state.container.roles
    roles.update(role["id"], system_prompt="AB")
    rev = roles.apply_persona_evolution(
        "role", role["id"], expected_body="AB", new_body="ABX", meta={}
    )
    roles.update(role["id"], system_prompt="AC")
    resp = client.post(
        f"/api/cards/persona/revisions/{rev['id']}/rollback",
        params={"scope": scope},
    )
    assert resp.status_code == 409
    assert "无法自动回退" in resp.json()["detail"]


def test_rollback_route_400_already_rolled_back(client):
    role = client.app.state.container.roles.create(name="R", system_prompt="a")
    scope = role_scope(role["id"])
    roles = client.app.state.container.roles
    roles.update(role["id"], system_prompt="b")
    rev = roles.apply_persona_evolution(
        "role", role["id"], expected_body="b", new_body="c", meta={}
    )
    first = client.post(
        f"/api/cards/persona/revisions/{rev['id']}/rollback",
        params={"scope": scope},
    )
    assert first.status_code == 200
    again = client.post(
        f"/api/cards/persona/revisions/{rev['id']}/rollback",
        params={"scope": scope},
    )
    assert again.status_code == 400
    assert "已经回退" in again.json()["detail"]


def test_proposal_routes(client):
    cards = client.app.state.container.knowledge_cards
    role = client.app.state.container.roles.create(name="R", system_prompt="")
    scope = role_scope(role["id"])
    prop = cards.persona_state.add_proposal(
        scope,
        target="doc",
        title="T",
        reason="R",
        basis=[{"card_id": "c1", "statement": "s"}],
    )
    acc = client.post(
        f"/api/cards/proposals/{prop['id']}/accept",
        params={"scope": scope},
    )
    assert acc.status_code == 200
    assert acc.json()["ok"] is True
    assert "request_text" in acc.json()
    dup = client.post(
        f"/api/cards/proposals/{prop['id']}/accept",
        params={"scope": scope},
    )
    assert dup.status_code == 400
    prop2 = cards.persona_state.add_proposal(
        scope, target="doc", title="T2", reason="R", basis=[]
    )
    dis = client.post(
        f"/api/cards/proposals/{prop2['id']}/dismiss",
        params={"scope": scope},
    )
    assert dis.status_code == 200
