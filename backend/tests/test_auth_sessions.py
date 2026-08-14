import json
from pathlib import Path

from app.auth.sessions import SessionStore


def test_create_and_validate(tmp_path: Path):
    store = SessionStore(tmp_path, ttl_days=7)
    sid = store.create()
    assert store.validate(sid) is True
    assert store.validate("nope") is False
    assert store.validate(None) is False


def test_revoke(tmp_path: Path):
    store = SessionStore(tmp_path, ttl_days=7)
    sid = store.create()
    store.revoke(sid)
    assert store.validate(sid) is False


def test_expired_session_invalid(tmp_path: Path, monkeypatch):
    store = SessionStore(tmp_path, ttl_days=0)  # 立即过期：实现用 ttl_seconds 更易测
    # 若实现仅支持天数，可用 monkeypatch 把 now 拨到未来
    sid = store.create()
    # 强制把 expires_at 写到过去
    path = tmp_path / ".kb" / "sessions.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data[sid]["expires_at"] = "2000-01-01T00:00:00+00:00"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert store.validate(sid) is False


def test_insert_if_absent_preserves_existing_and_adds_missing(tmp_path: Path):
    store = SessionStore(tmp_path)
    existing = store.create()
    path = tmp_path / ".kb" / "sessions.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    original_exp = data[existing]["expires_at"]
    store.insert_if_absent(existing)
    unchanged = json.loads(path.read_text(encoding="utf-8"))
    assert unchanged[existing]["expires_at"] == original_exp
    store.insert_if_absent("packed-sid")
    merged = json.loads(path.read_text(encoding="utf-8"))
    assert "packed-sid" in merged
    assert merged[existing]["expires_at"] == original_exp
