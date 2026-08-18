import time

from app.demo.guest_sessions import GuestSessionStore


def test_create_then_validate():
    store = GuestSessionStore()
    sid = store.create(ip="1.2.3.4")
    assert store.validate(sid) is True


def test_unknown_and_empty_session_is_invalid():
    store = GuestSessionStore()
    assert store.validate("nope") is False
    assert store.validate(None) is False


def test_expired_session_is_invalid():
    store = GuestSessionStore(ttl_seconds=0)
    sid = store.create()
    time.sleep(0.01)
    assert store.validate(sid) is False


def test_capacity_evicts_oldest():
    store = GuestSessionStore(capacity=2)
    first = store.create()
    second = store.create()
    third = store.create()
    assert store.validate(first) is False
    assert store.validate(second) is True
    assert store.validate(third) is True


def test_touch_message_counts_per_session():
    store = GuestSessionStore()
    sid = store.create()
    assert store.touch_message(sid) == 1
    assert store.touch_message(sid) == 2
    assert store.message_count(sid) == 2


def test_create_records_created_at():
    store = GuestSessionStore()
    before = time.monotonic()
    sid = store.create(ip="1.2.3.4")
    after = time.monotonic()
    with store._lock:
        session = store._sessions[sid]
    assert before <= session.created_at <= after
    assert session.expires_at > session.created_at


def test_store_writes_nothing_to_disk(tmp_path):
    """访客 session 落盘会污染演示知识库并造成并发写竞态。"""
    before = set(tmp_path.rglob("*"))
    store = GuestSessionStore()
    sid = store.create()
    store.validate(sid)
    store.touch_message(sid)
    assert set(tmp_path.rglob("*")) == before
