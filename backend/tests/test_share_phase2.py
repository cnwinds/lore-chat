"""分享 Phase 2：区间快照、密码解锁、访问统计。"""

from __future__ import annotations

from app.engine.share_snapshot import load_conversation_snapshot, snapshot_conversation
from app.models.share_links import ShareLinkStore, public_options
from app.models.share_unlocks import ShareUnlockStore, unlock_ttl_for_share


def _set_public_base(client, base: str):
    r = client.put("/api/admin/settings", json={"public_base_url": base})
    assert r.status_code == 200, r.text


def _seed_conversation(client) -> tuple[str, list[str]]:
    cid = client.post("/api/conversations").json()["id"]
    conv = client.post(
        f"/api/conversations/{cid}/messages",
        json={
            "messages": [
                {
                    "id": "m1",
                    "role": "user",
                    "text": "第一条",
                    "ts": "2026-08-24T10:00:00",
                    "status": "complete",
                },
                {
                    "id": "m2",
                    "role": "assistant",
                    "text": "第二条",
                    "ts": "2026-08-24T10:00:01",
                    "status": "complete",
                },
                {
                    "id": "m3",
                    "role": "user",
                    "text": "第三条",
                    "ts": "2026-08-24T10:00:02",
                    "status": "complete",
                },
            ]
        },
    ).json()
    ids = [m["id"] for m in conv["messages"]]
    assert len(ids) == 3
    return cid, ids


def _relogin(client):
    r = client.post("/api/auth/login", json={"password": "test-password-123"})
    assert r.status_code == 200, r.text


def test_snapshot_message_ids_filters_and_preserves_order(tmp_path):
    store = ShareLinkStore(tmp_path / "knowledge")
    conv = {
        "title": "t",
        "created_at": "x",
        "messages": [
            {"id": "a", "role": "user", "text": "1", "ts": "t", "status": "complete"},
            {"id": "b", "role": "assistant", "text": "2", "ts": "t", "status": "complete"},
            {"id": "c", "role": "user", "text": "3", "ts": "t", "status": "complete"},
        ],
    }
    # 请求顺序颠倒，快照仍应按会话原序
    ref = snapshot_conversation(
        conv,
        shares_dir=store.shares_dir,
        share_id="range01abcdefghij",
        message_ids=["c", "a"],
    )
    snap = load_conversation_snapshot(tmp_path / "knowledge", ref)
    ids = [m["id"] for m in snap["messages"]]
    assert ids == ["a", "c"]


def test_snapshot_unknown_message_id_raises(tmp_path):
    store = ShareLinkStore(tmp_path / "knowledge")
    conv = {
        "title": "t",
        "messages": [
            {"id": "a", "role": "user", "text": "1", "ts": "t", "status": "complete"},
        ],
    }
    try:
        snapshot_conversation(
            conv,
            shares_dir=store.shares_dir,
            share_id="range02abcdefghij",
            message_ids=["a", "missing"],
        )
        assert False, "expected ValueError"
    except ValueError as e:
        assert "unknown message_ids" in str(e)


def test_create_share_message_ids_range(client, tmp_path):
    _set_public_base(client, "https://share.example.com")
    cid, ids = _seed_conversation(client)
    mid_a, _mid_b, mid_c = ids
    r = client.post(
        "/api/shares",
        json={
            "type": "conversation",
            "conversation_id": cid,
            "message_ids": [mid_c, mid_a],
            "ttl_sec": 3600,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["options"]["message_count"] == 2
    assert data["options"]["message_ids"] == [mid_a, mid_c]
    assert "password_hash" not in data["options"]

    client.cookies.clear()
    pub = client.get(f"/api/share/{data['share_id']}")
    assert pub.status_code == 200
    msgs = pub.json()["messages"]
    assert [m["id"] for m in msgs] == [mid_a, mid_c]


def test_create_share_bad_message_ids_400(client):
    _set_public_base(client, "https://share.example.com")
    cid, ids = _seed_conversation(client)
    r = client.post(
        "/api/shares",
        json={
            "type": "conversation",
            "conversation_id": cid,
            "message_ids": [ids[0], "nope"],
        },
    )
    assert r.status_code == 400


def test_password_required_and_unlock(client):
    _set_public_base(client, "https://share.example.com")
    cid, _ids = _seed_conversation(client)
    r = client.post(
        "/api/shares",
        json={
            "type": "conversation",
            "conversation_id": cid,
            "password": "secret42",
            "ttl_sec": 86400,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["options"]["has_password"] is True
    assert "password_hash" not in data["options"]
    share_id = data["share_id"]

    client.cookies.clear()
    locked = client.get(f"/api/share/{share_id}")
    assert locked.status_code == 401
    detail = locked.json()["detail"]
    assert detail["code"] == "SHARE_PASSWORD_REQUIRED"

    # 401 不计访问
    _relogin(client)
    listed = client.get("/api/shares").json()["shares"]
    row = next(s for s in listed if s["share_id"] == share_id)
    assert row["view_count"] == 0

    client.cookies.clear()
    bad = client.post(
        f"/api/share/{share_id}/unlock",
        json={"password": "wrong"},
    )
    assert bad.status_code == 401

    unlocked = client.post(
        f"/api/share/{share_id}/unlock",
        json={"password": "secret42"},
    )
    assert unlocked.status_code == 200, unlocked.text
    token = unlocked.json()["unlock_token"]
    assert token

    # Cookie 路径
    pub = client.get(f"/api/share/{share_id}")
    assert pub.status_code == 200
    assert len(pub.json()["messages"]) == 3

    # Header 路径（清 cookie）
    client.cookies.clear()
    pub2 = client.get(
        f"/api/share/{share_id}",
        headers={"X-Share-Unlock": token},
    )
    assert pub2.status_code == 200

    _relogin(client)
    listed2 = client.get("/api/shares").json()["shares"]
    row2 = next(s for s in listed2 if s["share_id"] == share_id)
    assert row2["view_count"] == 2
    assert row2["last_viewed_at"]
    assert len(row2["recent_views"]) == 2


def test_password_wrong_unlock_token_still_401(client):
    _set_public_base(client, "https://share.example.com")
    cid, _ids = _seed_conversation(client)
    share_id = client.post(
        "/api/shares",
        json={
            "type": "conversation",
            "conversation_id": cid,
            "password": "pass1234",
        },
    ).json()["share_id"]
    client.cookies.clear()
    r = client.get(
        f"/api/share/{share_id}",
        headers={"X-Share-Unlock": "notarealtoken123456"},
    )
    assert r.status_code == 401


def test_no_password_behavior_unchanged(client):
    _set_public_base(client, "https://share.example.com")
    cid, _ids = _seed_conversation(client)
    share_id = client.post(
        "/api/shares",
        json={"type": "conversation", "conversation_id": cid},
    ).json()["share_id"]
    client.cookies.clear()
    assert client.get(f"/api/share/{share_id}").status_code == 200


def test_recent_views_ring_buffer(tmp_path):
    store = ShareLinkStore(tmp_path)
    link = store.create(
        type="conversation",
        title="t",
        payload_ref=".kb/shares/x.json",
        ttl_sec=None,
        share_id="viewstatsabcdefghij",
        now=1_000_000.0,
    )
    for i in range(25):
        store.resolve_public(
            link.share_id,
            now=1_000_000.0 + i,
            increment_view=True,
            referer=f"https://ref.example/{i}",
        )
    got = store.get(link.share_id)
    assert got is not None
    assert got.view_count == 25
    assert got.last_viewed_at
    assert len(got.recent_views) == 20
    assert got.recent_views[0]["referer"].endswith("/5")
    assert got.recent_views[-1]["referer"].endswith("/24")


def test_public_options_strips_hash():
    opts = public_options(
        {"password_hash": "bcrypt...", "message_ids": ["a"], "has_password": True}
    )
    assert "password_hash" not in opts
    assert opts["has_password"] is True
    assert opts["message_ids"] == ["a"]


def test_unlock_ttl_capped():
    now = 1_000_000.0
    assert unlock_ttl_for_share(None, now=now) == 24 * 3600
    assert unlock_ttl_for_share(now + 100, now=now) == 100
    assert unlock_ttl_for_share(now + 100_000, now=now) == 24 * 3600


def test_missing_snapshot_does_not_increment_views(client, tmp_path):
    _set_public_base(client, "https://share.example.com")
    cid, _ids = _seed_conversation(client)
    data = client.post(
        "/api/shares",
        json={"type": "conversation", "conversation_id": cid},
    ).json()
    share_id = data["share_id"]
    snap = tmp_path / "knowledge" / ".kb" / "shares" / f"{share_id}.json"
    assert snap.is_file()
    snap.unlink()

    client.cookies.clear()
    assert client.get(f"/api/share/{share_id}").status_code == 404

    _relogin(client)
    row = next(s for s in client.get("/api/shares").json()["shares"] if s["share_id"] == share_id)
    assert row["view_count"] == 0
    assert not row.get("recent_views")


def test_unlock_cookie_scoped_per_share(client):
    """不同分享的 unlock Cookie 不应互相覆盖。"""
    _set_public_base(client, "https://share.example.com")
    cid_a, _ = _seed_conversation(client)
    cid_b, _ = _seed_conversation(client)
    share_a = client.post(
        "/api/shares",
        json={
            "type": "conversation",
            "conversation_id": cid_a,
            "password": "passAAAA",
        },
    ).json()["share_id"]
    share_b = client.post(
        "/api/shares",
        json={
            "type": "conversation",
            "conversation_id": cid_b,
            "password": "passBBBB",
        },
    ).json()["share_id"]

    client.cookies.clear()
    assert (
        client.post(f"/api/share/{share_a}/unlock", json={"password": "passAAAA"}).status_code
        == 200
    )
    assert (
        client.post(f"/api/share/{share_b}/unlock", json={"password": "passBBBB"}).status_code
        == 200
    )
    assert client.get(f"/api/share/{share_a}").status_code == 200
    assert client.get(f"/api/share/{share_b}").status_code == 200


def test_unlock_store_expire(tmp_path):
    store = ShareUnlockStore(tmp_path)
    uid = store.issue("shareabc1234567890", ttl_sec=60, now=1_000.0)
    assert store.resolve(uid, now=1_010.0) is not None
    assert store.resolve(uid, now=1_100.0) is None


def test_live_conversation_share_follows_updates(client):
    _set_public_base(client, "https://share.example.com")
    cid, _ids = _seed_conversation(client)
    share_id = client.post(
        "/api/shares",
        json={
            "type": "conversation",
            "conversation_id": cid,
            "options": {"pin_version": False},
        },
    ).json()["share_id"]

    client.cookies.clear()
    pub1 = client.get(f"/api/share/{share_id}")
    assert pub1.status_code == 200
    assert len(pub1.json()["messages"]) == 3

    _relogin(client)
    client.post(
        f"/api/conversations/{cid}/messages",
        json={
            "messages": [
                {
                    "id": "live-msg-new-id-abcdefghij",
                    "role": "user",
                    "text": "分享后新增",
                    "ts": "2026-08-24T12:00:00",
                    "status": "complete",
                }
            ]
        },
    )

    client.cookies.clear()
    pub2 = client.get(f"/api/share/{share_id}")
    assert pub2.status_code == 200
    texts = [m.get("text") for m in pub2.json()["messages"]]
    assert len(texts) == 4
    assert "分享后新增" in texts


def test_live_conversation_rejects_message_ids(client):
    _set_public_base(client, "https://share.example.com")
    cid, ids = _seed_conversation(client)
    r = client.post(
        "/api/shares",
        json={
            "type": "conversation",
            "conversation_id": cid,
            "message_ids": [ids[0]],
            "options": {"pin_version": False},
        },
    )
    assert r.status_code == 400


def test_live_conversation_missing_returns_404(client):
    _set_public_base(client, "https://share.example.com")
    cid, _ids = _seed_conversation(client)
    share_id = client.post(
        "/api/shares",
        json={
            "type": "conversation",
            "conversation_id": cid,
            "options": {"pin_version": False},
        },
    ).json()["share_id"]
    _relogin(client)
    assert client.delete(f"/api/conversations/{cid}").status_code == 200
    client.cookies.clear()
    assert client.get(f"/api/share/{share_id}").status_code == 404
