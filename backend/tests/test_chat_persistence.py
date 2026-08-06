"""`/api/chat` 会话持久化：begin_turn/finalize_turn 顺序、409 重复、断流 interrupted。

见 docs/superpowers/plans/2026-07-14-second-brain-phase-1a.md Task 8
与 docs/superpowers/specs/2026-07-13-memory-layer-design.md §6.1。
"""
from __future__ import annotations

import asyncio
import json

from app.engine.agent.events import done, text_delta
from app.engine.conversations import ConversationStore, TurnInProgress


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_type = data = None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if event_type and data is not None:
            events.append((event_type, data))
    return events


def test_chat_persists_message_ids(client):
    cid = client.post("/api/conversations", json={"title": "t"}).json()["id"]
    r = client.post(
        "/api/chat",
        json={"text": "你好", "conversation_id": cid, "client_message_id": "cli-1"},
    )
    assert r.status_code == 200
    assert "done" in [t for t, _ in _parse_sse(r.text)]
    conv = client.get(f"/api/conversations/{cid}").json()
    msgs = conv["messages"]
    assert len(msgs) >= 2
    assert msgs[0]["role"] == "user" and msgs[0]["id"]
    assert msgs[1]["role"] == "assistant" and msgs[1]["id"]
    assert msgs[1].get("in_reply_to_message_id") == msgs[0]["id"]


def test_chat_duplicate_client_message_id_returns_409(client, monkeypatch):
    cid = client.post("/api/conversations", json={"title": "t"}).json()["id"]

    def boom(*a, **k):
        raise TurnInProgress("turn-x", retry_after_ms=500)

    monkeypatch.setattr(client.app.state.container.conversations, "begin_turn", boom)
    r = client.post(
        "/api/chat",
        json={"text": "你好", "conversation_id": cid, "client_message_id": "cli-x"},
    )
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == "turn_in_progress"
    assert detail["retry_after_ms"] == 500


def test_chat_complete_turn_replay_does_not_duplicate_messages(client):
    """相同 client_message_id 在成功完成后重试：应重放已存结果，不追加新消息。"""
    cid = client.post("/api/conversations", json={"title": "t"}).json()["id"]
    body = {"text": "你好", "conversation_id": cid, "client_message_id": "cli-replay"}

    r1 = client.post("/api/chat", json=body)
    assert r1.status_code == 200
    conv1 = client.get(f"/api/conversations/{cid}").json()
    assert len(conv1["messages"]) == 2

    r2 = client.post("/api/chat", json=body)
    assert r2.status_code == 200
    assert "done" in [t for t, _ in _parse_sse(r2.text)]

    conv2 = client.get(f"/api/conversations/{cid}").json()
    assert len(conv2["messages"]) == 2


def test_history_excludes_current_user_message(tmp_path):
    """路由必须在 begin_turn 之前快照历史；否则传给 Agent 的 history 会含本轮尚未回复的新消息。"""
    store = ConversationStore(tmp_path / "conversations")
    cid = store.create()
    store.begin_turn(
        cid, user_text="第一条", client_message_id="cli-1", observation_allowed=False
    )
    store.finalize_turn(
        cid,
        turn_id=store.get(cid)["active_turn_id"],
        assistant={"text": "回复一", "timeline": [], "sources": [], "status": "complete"},
    )

    history_before = ConversationStore.llm_history(store.get(cid))
    assert not any(m["content"] == "第二条" for m in history_before)

    store.begin_turn(
        cid, user_text="第二条", client_message_id="cli-2", observation_allowed=False
    )
    history_after = ConversationStore.llm_history(store.get(cid))
    assert any(m["content"] == "第二条" for m in history_after)
    # 证明为何路由必须在 begin_turn 之前快照历史：begin_turn 之后重新读取的
    # history 已经包含了本轮用户消息，若直接传给 Agent 会造成重复。
    assert history_before != history_after


def test_chat_agent_cancelled_finalizes_interrupted(client, monkeypatch):
    """Agent Task 内 CancelledError（显式 stop 路径）应落库 interrupted。"""
    cid = client.post("/api/conversations", json={"title": "t"}).json()["id"]
    container = client.app.state.container

    async def cancelling_run(self, user_text, **kwargs):
        yield text_delta("部分回复")
        raise asyncio.CancelledError()

    monkeypatch.setattr(
        type(container.agent), "run", cancelling_run, raising=True
    )

    try:
        client.post(
            "/api/chat",
            json={"text": "你好", "conversation_id": cid, "client_message_id": "cli-cancel"},
        )
    except Exception:
        pass

    conv = client.get(f"/api/conversations/{cid}").json()
    msgs = conv["messages"]
    assert len(msgs) == 2
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["status"] == "interrupted"
    assert msgs[1]["text"] == "部分回复"


def test_chat_stop_endpoint(client, monkeypatch):
    cid = client.post("/api/conversations", json={"title": "t"}).json()["id"]
    container = client.app.state.container

    async def slow_run(self, user_text, **kwargs):
        yield text_delta("running…")
        await asyncio.sleep(3600)

    monkeypatch.setattr(type(container.agent), "run", slow_run, raising=True)

    import threading
    import time

    err: list[BaseException] = []

    def post_chat():
        try:
            client.post(
                "/api/chat",
                json={
                    "text": "你好",
                    "conversation_id": cid,
                    "client_message_id": "cli-stop",
                },
            )
        except BaseException as e:
            err.append(e)

    t = threading.Thread(target=post_chat, daemon=True)
    t.start()
    for _ in range(100):
        if container.chat_runner.turn_hub.get_active(cid):
            break
        time.sleep(0.05)
    assert container.chat_runner.turn_hub.get_active(cid)

    r = client.post("/api/chat/stop", json={"conversation_id": cid})
    assert r.status_code == 200
    assert r.json()["status"] == "stopping"
    t.join(timeout=10)

    conv = client.get(f"/api/conversations/{cid}").json()
    assert conv.get("active_turn") is None
    assistant = [m for m in conv["messages"] if m["role"] == "assistant"]
    assert assistant
    assert assistant[-1]["status"] == "interrupted"


def test_finalize_turn_interrupted_directly(tmp_path):
    """不经 HTTP：直接覆盖 finalize_turn 的 interrupted 落库路径。"""
    store = ConversationStore(tmp_path / "conversations")
    cid = store.create()
    turn = store.begin_turn(
        cid, user_text="你好", client_message_id="cli-1", observation_allowed=False
    )
    result = store.finalize_turn(
        cid,
        turn_id=turn["turn_id"],
        assistant={
            "text": "部分回复",
            "timeline": [{"type": "text", "content": "部分回复", "ts": "t"}],
            "sources": [],
            "status": "interrupted",
        },
    )
    assert result is not None
    assert result["status"] == "interrupted"
    conv = store.get(cid)
    assert conv["messages"][1]["status"] == "interrupted"
