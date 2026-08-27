"""GET /api/conversations/{cid}/turns/active 轻量回合状态。"""


def test_active_turn_status_idle(client):
    cid = client.post("/api/conversations", json={"title": "t"}).json()["id"]
    r = client.get(f"/api/conversations/{cid}/turns/active")
    assert r.status_code == 200
    body = r.json()
    assert body["conversation_id"] == cid
    assert body["turn_id"] is None
    assert body["status"] is None
    assert body["observable"] is False


def test_active_turn_status_running_observable(client):
    cid = client.post("/api/conversations", json={"title": "t"}).json()["id"]
    stream = client.post(
        "/api/chat",
        json={
            "text": "hello",
            "conversation_id": cid,
            "client_message_id": "cli-active-status",
        },
    )
    assert stream.status_code == 200
    status = client.get(f"/api/conversations/{cid}/turns/active").json()
    assert status["status"] in ("running", None)
    if status["status"] == "running":
        assert status["observable"] is True
        assert status["turn_id"]
    stream.close()
