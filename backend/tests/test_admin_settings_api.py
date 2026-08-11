def test_get_and_put_settings(client):
    r = client.get("/api/admin/settings")
    assert r.status_code == 200
    body = r.json()
    assert "kb_path" in body
    assert "small_model" in body
    assert "search_cooldown" in body
    assert isinstance(body["search_cooldown"], dict)

    r2 = client.put("/api/admin/settings", json={"small_model": "hot-model-1"})
    assert r2.status_code == 200
    assert r2.json()["small_model"] == "hot-model-1"
    assert client.app.state.container.settings.small_model == "hot-model-1"
    assert "search_cooldown" in r2.json()

    r3 = client.get("/api/admin/settings")
    assert r3.json()["small_model"] == "hot-model-1"


def test_put_rejects_kb_path(client):
    r = client.put("/api/admin/settings", json={"kb_path": "/x"})
    assert r.status_code == 422


def test_put_duplicate_search_provider_returns_400(client):
    r = client.put(
        "/api/admin/settings",
        json={
            "search_providers": [
                {"id": "tavily", "provider": "tavily", "api_key": "a"},
                {"id": "t2", "provider": "tavily", "api_key": "b"},
            ]
        },
    )
    assert r.status_code == 400
    assert "duplicate" in str(r.json()["detail"]).lower()


def test_search_cooldown_clear(client):
    store = client.app.state.container.search_cooldown
    from app.models.cooldown import ErrorClass

    store.record_failure("tavily", ErrorClass.AUTH, error="bad key")
    assert store.get("tavily").disabled is True

    r = client.post(
        "/api/admin/search-cooldown/clear",
        json={"provider_id": "tavily"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert store.is_available("tavily")
    assert "search_cooldown" in r.json()
