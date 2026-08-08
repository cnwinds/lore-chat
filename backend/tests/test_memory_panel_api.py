from app.engine.memory.normalize import value_hash


def test_memory_panel_list_confirm_reject_edit_forget(client):
    store = client.app.state.container.memory_service.store
    stmt = "我似乎偏好简洁回答"
    cand = store.upsert_fact(
        slot_key="preference.response_style",
        category="preference",
        statement=stmt,
        normalized_value_hash=value_hash(stmt),
        origin="inferred",
        confidence=0.85,
        status="candidate",
    )
    store.add_session_evidence(cand["id"], "conv-abc")

    listed = client.get("/api/memory/facts")
    assert listed.status_code == 200
    facts = listed.json()["facts"]
    assert any(f["id"] == cand["id"] for f in facts)
    row = next(f for f in facts if f["id"] == cand["id"])
    assert "conv-abc" in row["conversation_ids"]

    # 同槽已有 confirmed 时，confirm 应 supersede 旧条
    old = store.upsert_fact(
        slot_key="preference.response_style",
        category="preference",
        statement="我偏好啰嗦回答",
        normalized_value_hash=value_hash("我偏好啰嗦回答"),
        origin="direct",
        confidence=0.9,
        status="confirmed",
    )
    conf = client.post(f"/api/memory/facts/{cand['id']}/confirm")
    assert conf.status_code == 200
    assert store.get_fact(cand["id"])["status"] == "confirmed"
    assert store.get_fact(old["id"])["status"] == "superseded"
    assert len(store.list_confirmed()) == 1

    edit = client.patch(
        f"/api/memory/facts/{cand['id']}",
        json={"statement": "我偏好简洁直接的回答"},
    )
    assert edit.status_code == 200
    assert "简洁直接" in store.get_fact(cand["id"])["statement"]

    forget = client.post(f"/api/memory/facts/{cand['id']}/forget")
    assert forget.status_code == 200
    assert store.list_confirmed() == []

    other = store.upsert_fact(
        slot_key="preference.cli_preparedness",
        category="preference",
        statement="我好像喜欢提前准备命令行",
        normalized_value_hash=value_hash("我好像喜欢提前准备命令行"),
        origin="inferred",
        confidence=0.8,
        status="candidate",
    )
    rej = client.post(f"/api/memory/facts/{other['id']}/reject")
    assert rej.status_code == 200
    assert store.get_fact(other["id"])["status"] == "rejected"
