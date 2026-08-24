"""分享 API 与快照集成测试。"""

from __future__ import annotations

import time

from app.engine.share_snapshot import snapshot_conversation
from app.models.share_links import ShareLinkStore


def _set_public_base(client, base: str):
    r = client.put("/api/admin/settings", json={"public_base_url": base})
    assert r.status_code == 200, r.text


def test_create_conversation_share_and_public_access(client, tmp_path):
    _set_public_base(client, "https://share.example.com")
    cid = client.post("/api/conversations").json()["id"]
    client.post(
        f"/api/conversations/{cid}/messages",
        json={
            "messages": [
                {
                    "id": "u1",
                    "role": "user",
                    "text": "Media Grant 不透明",
                    "ts": "2026-08-24T10:00:00",
                    "status": "complete",
                },
                {
                    "id": "a1",
                    "role": "assistant",
                    "text": "这是关于 Media Grant 的说明。",
                    "ts": "2026-08-24T10:00:01",
                    "status": "complete",
                },
            ]
        },
    )
    r = client.post(
        "/api/shares",
        json={
            "type": "conversation",
            "conversation_id": cid,
            "ttl_sec": 3600,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["url"].startswith("https://share.example.com/share/")
    share_id = data["share_id"]

    client.cookies.clear()
    pub = client.get(f"/api/share/{share_id}")
    assert pub.status_code == 200, pub.text
    body = pub.json()
    assert body["type"] == "conversation"
    assert len(body["messages"]) == 2

    # 追加消息不影响快照
    client.post(
        f"/api/conversations/{cid}/messages",
        json={
            "messages": [
                {
                    "id": "u2",
                    "role": "user",
                    "text": "后续消息",
                    "ts": "2026-08-24T11:00:00",
                    "status": "complete",
                }
            ]
        },
    )
    pub2 = client.get(f"/api/share/{share_id}")
    assert len(pub2.json()["messages"]) == 2


def test_doc_share_pinned(client, tmp_path):
    _set_public_base(client, "https://share.example.com")
    kb = tmp_path / "knowledge"
    doc_path = kb / "notes" / "share-me.md"
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text("# Hello\n\n分享文档正文", encoding="utf-8")
    rel = "notes/share-me.md"
    r = client.post(
        "/api/shares",
        json={
            "type": "doc",
            "path": rel,
            "options": {"pin_version": True},
        },
    )
    assert r.status_code == 200, r.text
    share_id = r.json()["share_id"]

    doc_path.write_text("已修改", encoding="utf-8")
    client.cookies.clear()
    pub = client.get(f"/api/share/{share_id}")
    assert pub.status_code == 200
    assert "Hello" in pub.json()["body"]


def test_revoked_share_not_accessible(client):
    _set_public_base(client, "https://share.example.com")
    cid = client.post("/api/conversations").json()["id"]
    r = client.post(
        "/api/shares",
        json={"type": "conversation", "conversation_id": cid},
    )
    share_id = r.json()["share_id"]
    assert client.delete(f"/api/shares/{share_id}").status_code == 200
    client.cookies.clear()
    assert client.get(f"/api/share/{share_id}").status_code == 404


def test_protected_doc_rejected(client):
    _set_public_base(client, "https://share.example.com")
    client.put(
        "/api/doc",
        json={"path": "系统/戒律.md", "body": "secret\n"},
    )
    r = client.post(
        "/api/shares",
        json={"type": "doc", "path": "系统/戒律.md"},
    )
    assert r.status_code == 400


def test_list_shares(client):
    _set_public_base(client, "https://share.example.com")
    cid = client.post("/api/conversations").json()["id"]
    client.post(
        "/api/shares",
        json={"type": "conversation", "conversation_id": cid},
    )
    listed = client.get("/api/shares").json()["shares"]
    assert any(s["type"] == "conversation" for s in listed)


def test_snapshot_conversation_file_written(tmp_path):
    store = ShareLinkStore(tmp_path / "knowledge")
    conv = {
        "title": "t",
        "created_at": "x",
        "messages": [{"id": "1", "role": "user", "text": "hi", "ts": "t", "status": "complete"}],
    }
    ref = snapshot_conversation(conv, shares_dir=store.shares_dir, share_id="snap01")
    assert ref == ".kb/shares/snap01.json"
    assert (store.shares_dir / "snap01.json").is_file()
