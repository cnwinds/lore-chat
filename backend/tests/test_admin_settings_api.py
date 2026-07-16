def test_get_and_put_settings(client):
    r = client.get("/api/admin/settings")
    assert r.status_code == 200
    body = r.json()
    assert "kb_path" in body
    assert "small_model" in body

    r2 = client.put("/api/admin/settings", json={"small_model": "hot-model-1"})
    assert r2.status_code == 200
    assert r2.json()["small_model"] == "hot-model-1"
    assert client.app.state.container.settings.small_model == "hot-model-1"

    r3 = client.get("/api/admin/settings")
    assert r3.json()["small_model"] == "hot-model-1"


def test_put_rejects_kb_path(client):
    r = client.put("/api/admin/settings", json={"kb_path": "/x"})
    assert r.status_code == 422
