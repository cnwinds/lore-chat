"""GET /api/admin/model-capabilities — single-model caps from lookup_capabilities."""


def test_model_capabilities_requires_model(client):
    r = client.get("/api/admin/model-capabilities")
    assert r.status_code == 422


def test_model_capabilities_agnes_prefix(client):
    r = client.get(
        "/api/admin/model-capabilities",
        params={"model": "agnes-2.5-flash", "base_url": "https://api.agnes-ai.com/v1"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["model"] == "agnes-2.5-flash"
    assert body["thinking"] is True
    assert body["image"] is True
    assert body["thinking_protocol"] == "agnes"
    assert body["image_wire"] == "url"
    assert body["effort_options"] == []
    assert "source" in body


def test_model_capabilities_unknown_uses_defaults(client):
    r = client.get(
        "/api/admin/model-capabilities",
        params={"model": "totally-unknown-model-xyz-99"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["thinking"] is False
    assert body["thinking_protocol"] == "none"
    assert body["image"] is False
