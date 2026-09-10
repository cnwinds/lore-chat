from app.engine.roles import DEFAULT_ROLE_ID, DEFAULT_ROLE_NAME, RoleStore
from app.engine.conversations import ConversationStore


def _roles(tmp_path):
    return RoleStore(tmp_path / "roles")


def _conv(tmp_path):
    return ConversationStore(tmp_path / "conversations")


def test_ensure_default_role(tmp_path):
    store = _roles(tmp_path)
    roles = store.list_all()
    assert len(roles) == 1
    assert roles[0]["id"] == DEFAULT_ROLE_ID
    assert roles[0]["name"] == DEFAULT_ROLE_NAME
    assert roles[0]["is_default"] is True


def test_create_and_delete_role(tmp_path):
    store = _roles(tmp_path)
    created = store.create(name="股票研究员", system_prompt="专注股票")
    assert created["name"] == "股票研究员"
    assert created["is_default"] is False
    assert len(store.list_all()) == 2
    store.delete(created["id"])
    assert len(store.list_all()) == 1


def test_cannot_delete_default(tmp_path):
    store = _roles(tmp_path)
    try:
        store.delete(DEFAULT_ROLE_ID)
        assert False, "should raise"
    except ValueError:
        pass


def test_conversation_role_id_default(tmp_path):
    conv = _conv(tmp_path)
    cid = conv.create()
    assert conv.get_role_id(cid) == DEFAULT_ROLE_ID
    items = conv.list_all()
    assert items[0]["role_id"] == DEFAULT_ROLE_ID


def test_ensure_active_ignores_stale_empty(tmp_path):
    """旧空会话不得劫持窗口内有消息的活跃线。"""
    from datetime import datetime, timedelta, timezone

    conv = _conv(tmp_path)
    stale = conv.create(role_id=DEFAULT_ROLE_ID)
    recent = conv.create(role_id=DEFAULT_ROLE_ID)
    conv.append_exchange(
        recent, "hello", {"role": "assistant", "text": "hi"}
    )
    now = datetime.now(timezone.utc)
    with conv._lock:
        conv.conn.execute(
            "UPDATE conversations SET updated_at = ?, last_user_message_at = ? WHERE id = ?",
            (
                (now - timedelta(days=30)).isoformat(),
                None,
                stale,
            ),
        )
        conv.conn.execute(
            "UPDATE conversations SET updated_at = ?, last_user_message_at = ? WHERE id = ?",
            (now.isoformat(), now.isoformat(), recent),
        )
        conv.conn.commit()
    active, created = conv.ensure_active_conversation(
        DEFAULT_ROLE_ID, idle_hours=6
    )
    assert active == recent
    assert created is False


def test_ensure_active_reuses_empty(tmp_path):
    conv = _conv(tmp_path)
    cid = conv.create(role_id=DEFAULT_ROLE_ID)
    again, created = conv.ensure_active_conversation(DEFAULT_ROLE_ID, idle_hours=6)
    assert again == cid
    assert created is False


def test_ensure_active_new_when_idle_expired(tmp_path, monkeypatch):
    conv = _conv(tmp_path)
    cid = conv.create(role_id=DEFAULT_ROLE_ID)
    conv.append_exchange(cid, "hello", {"role": "assistant", "text": "hi"})
    # Force last_user_message_at far in the past
    with conv._lock:
        conv.conn.execute(
            "UPDATE conversations SET last_user_message_at = ? WHERE id = ?",
            ("2020-01-01T00:00:00+00:00", cid),
        )
        conv.conn.commit()
    new_cid, created = conv.ensure_active_conversation(DEFAULT_ROLE_ID, idle_hours=6)
    assert new_cid != cid
    assert created is True


def test_reassign_role_conversations(tmp_path):
    roles = _roles(tmp_path)
    conv = _conv(tmp_path)
    created = roles.create(name="临时")
    cid = conv.create(role_id=created["id"])
    n = conv.reassign_role(created["id"], DEFAULT_ROLE_ID)
    assert n == 1
    assert conv.get_role_id(cid) == DEFAULT_ROLE_ID


def test_roles_list_uses_persona_and_last_active_at(client):
    created = client.post(
        "/api/roles",
        json={"name": "股票研究院", "system_prompt": "专注基本面研究"},
    )
    assert created.status_code == 200
    rid = created.json()["id"]
    cid = client.post(f"/api/roles/{rid}/ensure-active").json()["conversation_id"]
    store = client.app.state.container.conversations
    turn = store.begin_turn(
        cid, "帮我看看今天行情", "cli-last-msg", observation_allowed=False
    )
    listed = client.get("/api/roles").json()["roles"]
    row = next(x for x in listed if x["id"] == rid)
    assert row["system_prompt"] == "专注基本面研究"
    assert "帮我看看今天行情" not in row["system_prompt"]
    meta = store.get_turn(turn["turn_id"])
    assert meta is not None
    assert row["last_active_at"] == meta["started_at"]


def test_roles_last_active_at_ignores_empty_conversation(client):
    created = client.post(
        "/api/roles",
        json={"name": "还没聊", "system_prompt": "空着"},
    )
    assert created.status_code == 200
    rid = created.json()["id"]
    client.post(f"/api/roles/{rid}/ensure-active")
    listed = client.get("/api/roles").json()["roles"]
    row = next(x for x in listed if x["id"] == rid)
    assert row["last_active_at"] is None


def test_roles_http_api(client):
    r = client.get("/api/roles")
    assert r.status_code == 200
    roles = r.json()["roles"]
    assert len(roles) >= 1
    assert any(x["is_default"] for x in roles)

    created = client.post(
        "/api/roles",
        json={"name": "新闻助手", "system_prompt": "关注新闻"},
    )
    assert created.status_code == 200
    rid = created.json()["id"]
    assert created.json()["system_prompt"] == "关注新闻"

    active = client.post(f"/api/roles/{rid}/ensure-active")
    assert active.status_code == 200
    cid = active.json()["conversation_id"]
    assert "created" in active.json()
    conv = client.get(f"/api/conversations/{cid}")
    assert conv.status_code == 200
    assert conv.json()["role_id"] == rid

    made = client.post("/api/conversations", json={"role_id": rid})
    assert made.status_code == 200
    assert made.json()["role_id"] == rid

    deleted = client.delete(f"/api/roles/{rid}")
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True
    # 会话应迁回默认角色
    after = client.get(f"/api/conversations/{cid}")
    assert after.status_code == 200
    assert after.json()["role_id"] == "default"

    bad = client.delete("/api/roles/default")
    assert bad.status_code == 400


def test_conversations_search_http(client):
    from app.index.message_chunk import MessageChunk

    empty = client.get("/api/conversations/search", params={"q": ""})
    assert empty.status_code == 200
    assert empty.json()["hits"] == []

    created = client.post("/api/conversations", json={})
    assert created.status_code == 200
    cid = created.json()["id"]
    store = client.app.state.container.conversations
    fts = client.app.state.container.conversation_fts
    store.append_exchange(
        cid,
        "讨论 continuity 连续窗口",
        {"role": "assistant", "text": "连续窗口用于活跃线"},
    )
    conv = store.get(cid)
    for m in conv["messages"]:
        text = m.get("text") or ""
        fts.upsert_message_chunks(
            conversation_id=cid,
            message_id=m["id"],
            role=m["role"],
            ts=m.get("ts") or "",
            conversation_title=conv["title"],
            chunks=[MessageChunk(0, 0, len(text), text)],
        )
    hit = client.get(
        "/api/conversations/search", params={"q": "连续窗口", "k": 10}
    )
    assert hit.status_code == 200
    data = hit.json()
    assert any(h["conversation_id"] == cid for h in data["hits"])


def test_role_system_prompt_in_build(tmp_path):
    from app.engine.agent.prompts import build_system_prompt

    text = build_system_prompt(role_system_prompt="你是股票研究员")
    assert "股票研究员" in text
    assert "【当前角色】" in text


def test_role_schedules_crud(tmp_path):
    store = _roles(tmp_path)
    rid = store.create(name="定时角色")["id"]
    s = store.schedules.create(
        rid, prompt="每日简报", interval_hours=24, enabled=True
    )
    assert s["prompt"] == "每日简报"
    assert s["enabled"] is True
    listed = store.schedules.list_for_role(rid)
    assert len(listed) == 1
    updated = store.schedules.update(s["id"], enabled=False)
    assert updated["enabled"] is False
    store.schedules.delete(s["id"])
    assert store.schedules.list_for_role(rid) == []


def test_role_schedule_daily_timing(tmp_path):
    store = _roles(tmp_path)
    rid = store.create(name="日历定时")["id"]
    s = store.schedules.create(
        rid,
        prompt="早报",
        timing={"kind": "daily", "hour": 9, "minute": 0},
        enabled=True,
    )
    assert s["kind"] == "daily"
    assert s["timing"]["hour"] == 9
    assert "每天 09:00" in s["timing_summary"]
    assert s["next_run_at"]


def test_role_schedules_and_busy_http(client):
    created = client.post(
        "/api/roles", json={"name": "忙角色", "system_prompt": "处理忙碌态"}
    )
    assert created.status_code == 200
    rid = created.json()["id"]

    busy = client.get("/api/roles/busy")
    assert busy.status_code == 200
    assert isinstance(busy.json()["role_ids"], list)

    sched = client.post(
        f"/api/roles/{rid}/schedules",
        json={"prompt": "提醒一下", "interval_hours": 12},
    )
    assert sched.status_code == 200
    sid = sched.json()["id"]
    listed = client.get(f"/api/roles/{rid}/schedules")
    assert listed.status_code == 200
    assert any(x["id"] == sid for x in listed.json()["schedules"])

    patched = client.patch(
        f"/api/roles/{rid}/schedules/{sid}",
        json={"enabled": False},
    )
    assert patched.status_code == 200
    assert patched.json()["enabled"] is False

    deleted = client.delete(f"/api/roles/{rid}/schedules/{sid}")
    assert deleted.status_code == 200

    daily = client.post(
        f"/api/roles/{rid}/schedules",
        json={
            "prompt": "早报",
            "timing": {"kind": "daily", "hour": 9, "minute": 0},
        },
    )
    assert daily.status_code == 200
    body = daily.json()
    assert body["kind"] == "daily"
    assert "每天 09:00" in body["timing_summary"]


def test_role_schedule_runs_http(client):
    created = client.post(
        "/api/roles", json={"name": "定时角色", "system_prompt": "跑定时"}
    )
    assert created.status_code == 200
    rid = created.json()["id"]
    sched = client.post(
        f"/api/roles/{rid}/schedules",
        json={"prompt": "每日简报", "interval_hours": 24},
    )
    assert sched.status_code == 200
    sid = sched.json()["id"]

    empty = client.get(f"/api/roles/{rid}/schedules/{sid}/runs")
    assert empty.status_code == 200
    assert empty.json()["runs"] == []

    cid = client.post(f"/api/roles/{rid}/ensure-active").json()["conversation_id"]
    store = client.app.state.container.conversations
    turn = store.begin_turn(
        cid,
        "每日简报",
        f"role-schedule:{sid}:abc123",
        observation_allowed=False,
    )
    store.finalize_turn(
        cid,
        turn_id=turn["turn_id"],
        assistant={
            "text": "今日无重大事项",
            "timeline": [
                {"type": "text", "content": "今日无重大事项", "ts": "t"}
            ],
            "sources": [],
            "status": "complete",
        },
    )

    listed = client.get(f"/api/roles/{rid}/schedules/{sid}/runs")
    assert listed.status_code == 200
    runs = listed.json()["runs"]
    assert len(runs) == 1
    assert runs[0]["summary"] == "今日无重大事项"
    assert runs[0]["status"] == "complete"
    assert runs[0]["turn_id"] == turn["turn_id"]

    other = client.post(
        "/api/roles", json={"name": "别人", "system_prompt": "无权看"}
    )
    assert other.status_code == 200
    forbidden = client.get(
        f"/api/roles/{other.json()['id']}/schedules/{sid}/runs"
    )
    assert forbidden.status_code == 404


def test_create_role_tool(tmp_path):
    from app.engine.agent.tool_impl.role_tools import RoleTools

    store = _roles(tmp_path)
    tools = RoleTools(store)
    out = tools.create_role({"name": "工具角色", "system_prompt": "专注工具"})
    assert "error" not in out
    assert out["role"]["name"] == "工具角色"
    assert len(store.list_all()) == 2


def test_busy_role_ids_from_running_turn(tmp_path):
    roles = _roles(tmp_path)
    conv = _conv(tmp_path)
    created = roles.create(name="跑着")
    cid = conv.create(role_id=created["id"])
    assert conv.list_busy_role_ids() == []
    turn = conv.begin_turn(
        cid,
        "hi",
        "client-1",
        observation_allowed=False,
    )
    assert turn["status"] == "running" or True
    assert created["id"] in conv.list_busy_role_ids()
    assert conv.role_has_running_turn(created["id"]) is True


def test_list_timeline_ascending(tmp_path):
    from datetime import datetime, timedelta, timezone

    conv = _conv(tmp_path)
    a = conv.create(role_id=DEFAULT_ROLE_ID, title="旧")
    b = conv.create(role_id=DEFAULT_ROLE_ID, title="新")
    conv.append_exchange(a, "old", {"role": "assistant", "text": "ok"})
    now = datetime.now(timezone.utc)
    with conv._lock:
        conv.conn.execute(
            "UPDATE conversations SET created_at = ? WHERE id = ?",
            ((now - timedelta(hours=2)).isoformat(), a),
        )
        conv.conn.execute(
            "UPDATE conversations SET created_at = ? WHERE id = ?",
            (now.isoformat(), b),
        )
        conv.conn.commit()
    segs, has_more = conv.list_timeline(
        DEFAULT_ROLE_ID, include_messages=True, only_with_messages=False
    )
    ids = [s["id"] for s in segs]
    assert ids.index(a) < ids.index(b)
    assert any(s["id"] == a and s["messages"] for s in segs)
    assert has_more is False


def test_list_timeline_pagination(tmp_path):
    from datetime import datetime, timedelta, timezone

    conv = _conv(tmp_path)
    now = datetime.now(timezone.utc)
    ids = []
    for i in range(6):
        cid = conv.create(role_id=DEFAULT_ROLE_ID, title=f"s{i}")
        conv.append_exchange(cid, f"u{i}", {"role": "assistant", "text": f"a{i}"})
        ids.append(cid)
        with conv._lock:
            conv.conn.execute(
                "UPDATE conversations SET created_at = ? WHERE id = ?",
                ((now - timedelta(hours=6 - i)).isoformat(), cid),
            )
            conv.conn.commit()
    page, has_more = conv.list_timeline(
        DEFAULT_ROLE_ID, include_messages=True, limit=2
    )
    assert has_more is True
    assert [s["id"] for s in page] == ids[-2:]
    oldest = page[0]
    older, has_more2 = conv.list_timeline(
        DEFAULT_ROLE_ID,
        include_messages=True,
        limit=2,
        before_created_at=oldest["created_at"],
        before_id=oldest["id"],
    )
    assert [s["id"] for s in older] == ids[-4:-2]
    assert has_more2 is True


def test_open_new_topic_reuses_empty_tip(tmp_path):
    conv = _conv(tmp_path)
    empty = conv.create(role_id=DEFAULT_ROLE_ID)
    assert conv.open_new_topic(DEFAULT_ROLE_ID) == empty


def test_ensure_active_outside_window_closes_previous(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone

    conv = _conv(tmp_path)
    old = conv.create(role_id=DEFAULT_ROLE_ID)
    conv.append_exchange(old, "hello", {"role": "assistant", "text": "hi"})
    now = datetime.now(timezone.utc)
    with conv._lock:
        conv.conn.execute(
            "UPDATE conversations SET updated_at = ?, last_user_message_at = ? WHERE id = ?",
            (
                (now - timedelta(hours=10)).isoformat(),
                (now - timedelta(hours=10)).isoformat(),
                old,
            ),
        )
        conv.conn.commit()

    called: list[str] = []

    def _capture(cid: str) -> bool:
        called.append(cid)
        return True

    monkeypatch.setattr(conv, "request_immediate_memory_extract", _capture)
    tip, created = conv.ensure_active_conversation(DEFAULT_ROLE_ID, idle_hours=6)
    assert created is True
    assert tip != old
    assert old in called


def test_reassign_role_preserves_updated_at(tmp_path):
    """删角色迁会话不得把目标角色 tip 劫持为迁入会话。"""
    from datetime import datetime, timedelta, timezone

    roles = _roles(tmp_path)
    conv = _conv(tmp_path)
    other = roles.create(name="其它")
    default_tip = conv.create(role_id=DEFAULT_ROLE_ID)
    conv.append_exchange(
        default_tip, "keep", {"role": "assistant", "text": "ok"}
    )
    moved = conv.create(role_id=other["id"])
    conv.append_exchange(moved, "x", {"role": "assistant", "text": "y"})
    now = datetime.now(timezone.utc)
    with conv._lock:
        conv.conn.execute(
            "UPDATE conversations SET updated_at = ?, last_user_message_at = ? WHERE id = ?",
            (now.isoformat(), now.isoformat(), default_tip),
        )
        conv.conn.execute(
            "UPDATE conversations SET updated_at = ?, last_user_message_at = ? WHERE id = ?",
            (
                (now - timedelta(days=1)).isoformat(),
                (now - timedelta(days=1)).isoformat(),
                moved,
            ),
        )
        conv.conn.commit()
    before = conv.get(moved)["updated_at"]
    conv.reassign_role(other["id"], DEFAULT_ROLE_ID)
    assert conv.get(moved)["updated_at"] == before
    active, _ = conv.ensure_active_conversation(DEFAULT_ROLE_ID, idle_hours=6)
    assert active == default_tip


def test_list_timeline_limit_excludes_empty_tip_from_quota(tmp_path):
    from datetime import datetime, timedelta, timezone

    conv = _conv(tmp_path)
    now = datetime.now(timezone.utc)
    ids = []
    for i in range(3):
        cid = conv.create(role_id=DEFAULT_ROLE_ID, title=f"h{i}")
        conv.append_exchange(cid, f"u{i}", {"role": "assistant", "text": f"a{i}"})
        ids.append(cid)
        with conv._lock:
            conv.conn.execute(
                "UPDATE conversations SET created_at = ? WHERE id = ?",
                ((now - timedelta(hours=3 - i)).isoformat(), cid),
            )
            conv.conn.commit()
    tip = conv.create(role_id=DEFAULT_ROLE_ID, title="tip")
    page, has_more = conv.list_timeline(
        DEFAULT_ROLE_ID,
        include_messages=True,
        limit=2,
        tip_id=tip,
        only_with_messages=True,
    )
    assert has_more is True
    assert page[-1]["id"] == tip
    assert [s["id"] for s in page[:-1]] == ids[-2:]


def test_should_prefetch_role_context():
    from app.engine.chat.role_context_prefetch import should_prefetch_role_context

    assert should_prefetch_role_context([]) is True
    assert should_prefetch_role_context(None) is True
    assert should_prefetch_role_context([{"role": "assistant", "content": "x"}]) is True
    assert (
        should_prefetch_role_context([{"role": "user", "content": "hi"}]) is False
    )
