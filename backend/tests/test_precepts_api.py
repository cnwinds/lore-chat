from app.engine.agent import system_layer as sl


def _conflict_pending(client, monkeypatch):
    c = client.app.state.container
    live = c.repo.read_doc("系统/戒律.md").body.replace("宁可不记", "必须先问用户", 1)
    doc = c.repo.read_doc("系统/戒律.md")
    c.knowledge_writer.persist_document(
        "系统/戒律.md",
        doc.meta,
        live,
        commit_msg="user precepts",
        changelog_line="改戒律",
    )
    monkeypatch.setattr(
        sl, "_PRECEPTS_BODY", sl._PRECEPTS_BODY.replace("宁可不记", "宁可先不记", 1)
    )
    return c.precepts_upgrade.sync()


def test_precepts_upgrade_get_current(client):
    r = client.get("/api/precepts/upgrade")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["path"] == "系统/戒律.md"
    assert data["status"] == "current"
    assert data["pending"] is None


def test_precepts_upgrade_confirm_and_dismiss(client, monkeypatch):
    st = _conflict_pending(client, monkeypatch)
    assert st.status == "pending_review"
    r = client.get("/api/precepts/upgrade")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "pending_review"
    assert data["pending"]["conflicts"]

    bad = client.post(
        "/api/precepts/upgrade/confirm",
        json={"body": "<<<<<<< 当前\nx\n>>>>>>> 新官方\n"},
    )
    assert bad.status_code == 400

    body = "# 戒律 · 行为规约\n必须先问；宁可先不记。\n"
    ok = client.post("/api/precepts/upgrade/confirm", json={"body": body})
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "applied"
    assert client.app.state.container.repo.read_doc("系统/戒律.md").body == body
    assert "<<<<<<<" not in body


def test_precepts_upgrade_dismiss_api(client, monkeypatch):
    _conflict_pending(client, monkeypatch)
    r = client.post("/api/precepts/upgrade/dismiss")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "current"
    live = client.app.state.container.repo.read_doc("系统/戒律.md").body
    assert "必须先问用户" in live
    again = client.get("/api/precepts/upgrade")
    assert again.json()["status"] == "current"
