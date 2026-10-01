def test_background_endpoints(client):
    r = client.get("/api/admin/background")
    assert r.status_code == 200
    body = r.json()
    assert "lanes" in body and "nodes" in body and "status" in body
    assert body["status"]["backlog"]["session_observe_pending"] >= 0

    r2 = client.get("/api/admin/background/status")
    assert r2.status_code == 200
    assert "workers" in r2.json()

    r3 = client.get(
        "/api/admin/background/calls",
        params={"purpose": "memory.owner_extract", "limit": 5},
    )
    assert r3.status_code == 200
    assert "calls" in r3.json()

    r4 = client.get("/api/admin/background/calls/999999")
    assert r4.status_code == 404


def test_background_settings_pause_calls_and_idle_hours(client):
    put_pause = client.put(
        "/api/admin/settings",
        json={"background_paused": ["persona_evolution", "bogus"]},
    )
    assert put_pause.status_code == 200
    status = client.get("/api/admin/background/status").json()
    assert status["paused"] == ["persona_evolution"]

    blog = client.app.state.container.background_call_log
    blog.record(
        purpose="memory.owner_extract",
        variant=None,
        model="test-model",
        model_label="Test",
        candidate_id=None,
        chain="utility",
        temperature=0.1,
        api_messages=[
            {"role": "system", "content": "catalog system"},
            {"role": "user", "content": "user line"},
        ],
        response='{"items":[]}',
        status="ok",
        error=None,
        duration_ms=12,
        prompt_tokens=10,
        completion_tokens=5,
        conversation_id="conv-contract",
        scope=None,
    )
    listed = client.get(
        "/api/admin/background/calls",
        params={"purpose": "memory.owner_extract", "limit": 10},
    )
    assert listed.status_code == 200
    calls = listed.json()["calls"]
    assert any(c["conversation_id"] == "conv-contract" for c in calls)
    call_id = next(c["id"] for c in calls if c["conversation_id"] == "conv-contract")
    detail = client.get(f"/api/admin/background/calls/{call_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["params"]["temperature"] == 0.1
    assert body["messages"][0]["content"] == "catalog system"
    assert body["response"] == '{"items":[]}'

    put_idle = client.put("/api/admin/settings", json={"memory_session_idle_hours": 6})
    assert put_idle.status_code == 200
    overview = client.get("/api/admin/background").json()
    session_lane = next(l for l in overview["lanes"] if l["id"] == "session_observe")
    assert "6 小时" in session_lane["cadence"]
    assert client.app.state.container.memory_worker.idle_hours == 6.0
