from datetime import datetime, timedelta, timezone

from app.deps import build_container
from app.config import Settings
from app.engine.memory_worker import MemoryWorker
from tests.helpers import preference_action, scripted_memory_extractor


def test_worker_processes_session_job_and_confirms_direct(tmp_path):
    kb = tmp_path / "knowledge"
    kb.mkdir()
    container = build_container(Settings(kb_path=kb))
    store = container.conversations
    cid = store.create()
    turn = store.begin_turn(
        cid, user_text="我偏好简洁回答", client_message_id="c1", observation_allowed=True
    )
    store.finalize_turn(
        cid,
        turn["turn_id"],
        assistant={"text": "好的", "timeline": [], "sources": [], "status": "complete"},
    )
    past = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    store.conn.execute(
        "UPDATE conversations SET last_user_message_at = ? WHERE id = ?",
        (past, cid),
    )
    store.conn.commit()
    worker = MemoryWorker(
        store,
        container.memory_service,
        extractor=scripted_memory_extractor(preference_action("我偏好简洁回答")),
        idle_hours=0,
    )
    assert worker.drain(max_jobs=5) >= 1
    assert container.memory_service.store.list_confirmed()


def test_memory_updated_event_after_confirm(tmp_path, client):
    container = client.app.state.container
    store = container.conversations
    cid = store.create()
    turn = store.begin_turn(
        cid, user_text="我偏好简洁回答", client_message_id="c1", observation_allowed=True
    )
    store.finalize_turn(
        cid,
        turn["turn_id"],
        assistant={"text": "好的", "timeline": [], "sources": [], "status": "complete"},
    )
    past = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    store.conn.execute(
        "UPDATE conversations SET last_user_message_at = ? WHERE id = ?",
        (past, cid),
    )
    store.conn.commit()
    worker = MemoryWorker(
        store,
        container.memory_service,
        extractor=scripted_memory_extractor(preference_action("我偏好简洁回答")),
        idle_hours=0,
    )
    worker.drain(max_jobs=5)
    events = store.list_system_events(cid)
    assert events
    assert events[0]["event_type"] == "memory_updated"
    assert events[0]["payload"]["type"] == "memory_updated"


def test_events_api_after_event_id(tmp_path, client):
    container = client.app.state.container
    store = container.conversations
    cid = store.create()
    e1 = store.append_system_event(cid, "memory_updated", {"type": "memory_updated", "count": 1})
    e2 = store.append_system_event(cid, "memory_updated", {"type": "memory_updated", "count": 2})
    r = client.get(f"/api/conversations/{cid}/events", params={"after_event_id": e1["id"]})
    assert r.status_code == 200
    ids = [ev["id"] for ev in r.json()["events"]]
    assert e2["id"] in ids
    assert e1["id"] not in ids
