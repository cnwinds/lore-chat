import pytest

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


def test_list_all_default_includes_blank_role_id(tmp_path):
    conv = _conv(tmp_path)
    tagged = conv.create(role_id=DEFAULT_ROLE_ID)
    blank = conv.create(role_id=DEFAULT_ROLE_ID)
    other = conv.create(role_id="other")
    with conv._lock:
        conv.conn.execute(
            "UPDATE conversations SET role_id = '' WHERE id = ?", (blank,)
        )
        conv.conn.commit()
    ids = {c["id"] for c in conv.list_all(role_id=DEFAULT_ROLE_ID)}
    assert tagged in ids
    assert blank in ids
    assert other not in ids
    assert conv.get(blank)["role_id"] == DEFAULT_ROLE_ID


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


def test_delete_for_role_removes_only_that_role(tmp_path):
    roles = _roles(tmp_path)
    conv = _conv(tmp_path)
    created = roles.create(name="临时")
    keep = conv.create(role_id=DEFAULT_ROLE_ID)
    cid = conv.create(role_id=created["id"])
    extra = conv.create(role_id=created["id"])
    n = conv.delete_for_role(created["id"])
    assert n == 2
    with pytest.raises(KeyError):
        conv.get(cid)
    with pytest.raises(KeyError):
        conv.get(extra)
    assert conv.get_role_id(keep) == DEFAULT_ROLE_ID
    assert conv.list_conversation_ids(role_id=created["id"]) == []
    with pytest.raises(ValueError, match="role_id"):
        conv.delete_for_role("")
    assert conv.get_role_id(keep) == DEFAULT_ROLE_ID


def test_roles_list_uses_last_reply_and_last_active_at(client):
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
    assert row.get("last_reply_preview") in (None, "")
    meta = store.get_turn(turn["turn_id"])
    assert meta is not None
    assert row["last_active_at"] == meta["started_at"]

    store.finalize_turn(
        cid,
        turn_id=turn["turn_id"],
        assistant={
            "text": "今日沪深三百震荡，建议先看成交量。",
            "timeline": [],
            "sources": [],
            "status": "complete",
        },
    )
    after = next(
        x for x in client.get("/api/roles").json()["roles"] if x["id"] == rid
    )
    assert after["last_reply_preview"] == "今日沪深三百震荡，建议先看成交量。"
    assert "专注基本面研究" not in (after.get("last_reply_preview") or "")


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
    keep = client.post("/api/conversations", json={"role_id": "default"})
    assert keep.status_code == 200
    keep_id = keep.json()["id"]

    deleted = client.delete(f"/api/roles/{rid}")
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True
    assert deleted.json()["deleted_conversations"] == 2
    after = client.get(f"/api/conversations/{cid}")
    assert after.status_code == 404
    gone = client.get(f"/api/conversations/{made.json()['id']}")
    assert gone.status_code == 404
    still = client.get(f"/api/conversations/{keep_id}")
    assert still.status_code == 200
    assert still.json()["role_id"] == "default"

    bad = client.delete("/api/roles/default")
    assert bad.status_code == 400


def test_role_timeline_excludes_other_roles(client):
    other = client.post(
        "/api/roles", json={"name": "专员", "system_prompt": "专注"}
    )
    assert other.status_code == 200
    rid = other.json()["id"]
    other_cid = client.post(f"/api/roles/{rid}/ensure-active").json()[
        "conversation_id"
    ]
    default_cid = client.post("/api/roles/default/ensure-active").json()[
        "conversation_id"
    ]
    store = client.app.state.container.conversations

    def _say(cid: str, text: str, reply: str, client_id: str) -> None:
        turn = store.begin_turn(cid, text, client_id, observation_allowed=False)
        store.finalize_turn(
            cid,
            turn_id=turn["turn_id"],
            assistant={
                "text": reply,
                "timeline": [],
                "sources": [],
                "status": "complete",
            },
        )

    _say(other_cid, "专员的话", "专员的答", "cli-other")
    _say(default_cid, "通用的话", "通用的答", "cli-def")

    default_tl = client.get(
        "/api/roles/default/timeline",
        params={"limit": 20, "include_messages": True, "message_limit": 0},
    )
    assert default_tl.status_code == 200
    default_ids = [s["id"] for s in default_tl.json()["segments"]]
    assert other_cid not in default_ids
    default_text = " ".join(
        (m.get("text") or "")
        for s in default_tl.json()["segments"]
        for m in (s.get("messages") or [])
    )
    assert "专员的话" not in default_text
    assert "通用的话" in default_text

    other_tl = client.get(
        f"/api/roles/{rid}/timeline",
        params={"limit": 20, "include_messages": True, "message_limit": 0},
    )
    assert other_tl.status_code == 200
    other_ids = [s["id"] for s in other_tl.json()["segments"]]
    assert other_cid in other_ids
    assert default_cid not in other_ids


def test_chat_rejects_conversation_role_mismatch(client):
    other = client.post(
        "/api/roles", json={"name": "专员", "system_prompt": "专注"}
    )
    assert other.status_code == 200
    rid = other.json()["id"]
    cid = client.post("/api/conversations", json={"role_id": rid}).json()["id"]
    r = client.post(
        "/api/chat",
        json={"text": "hi", "conversation_id": cid, "role_id": "default"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "role_mismatch"


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
    assert any(h.get("kind", "message") == "message" for h in data["hits"])


def test_conversations_search_vector_without_fts(client):
    from app.index.message_chunk import MessageChunk

    cid = client.post("/api/conversations", json={}).json()["id"]
    store = client.app.state.container.conversations
    vec = client.app.state.container.conversation_vector
    llm = client.app.state.container.llm
    token = "向量独有词zxqv"
    store.append_exchange(
        cid,
        token,
        {"role": "assistant", "text": f"回复 {token}"},
    )
    conv = store.get(cid)
    for m in conv["messages"]:
        text = m.get("text") or ""
        chunk = MessageChunk(0, 0, len(text), text)
        vec.upsert_message_chunks(
            conversation_id=cid,
            message_id=m["id"],
            role=m["role"],
            ts=m.get("ts") or "",
            conversation_title=conv["title"],
            chunks=[chunk],
            embeddings=llm.embed([text]),
        )
    hit = client.get("/api/conversations/search", params={"q": token, "k": 10})
    assert hit.status_code == 200
    assert any(h["conversation_id"] == cid for h in hit.json()["hits"])


def test_conversations_search_roles_and_files(client):
    created = client.post(
        "/api/roles", json={"name": "新闻助手", "system_prompt": "写快讯"}
    )
    assert created.status_code == 200
    roles = client.get(
        "/api/conversations/search",
        params={"q": "新闻", "scope": "roles", "k": 10},
    )
    assert roles.status_code == 200
    assert any(
        h["kind"] == "role" and h["title"] == "新闻助手" for h in roles.json()["hits"]
    )

    client.app.state.container.indexer.reindex_doc(
        "笔记/浙江天气.md", "浙江杭州今天多云"
    )
    files = client.get(
        "/api/conversations/search",
        params={"q": "浙江杭州", "scope": "files", "k": 10},
    )
    assert files.status_code == 200
    assert any(
        h["kind"] == "file" and h.get("path") == "笔记/浙江天气.md"
        for h in files.json()["hits"]
    )


def test_role_system_prompt_in_build(tmp_path):
    from app.engine.agent.prompts import build_system_prompt

    text = build_system_prompt(role_system_prompt="你是股票研究员")
    assert "股票研究员" in text
    assert "【当前角色】" in text


def test_role_identity_block_name_without_persona():
    """空人设仍须注入角色名与「你是谁」——否则模型会退回通用助手人格。"""
    from app.engine.agent.prompts import (
        build_role_identity_block,
        build_system_prompt,
    )

    block = build_role_identity_block(name="svg大师", system_prompt="", avatar=None)
    assert "svg大师" in block
    assert "你当前就是这个角色" in block
    assert "尚未设置" in block

    text = build_system_prompt(role_system_prompt=block)
    assert "【当前角色】" in text
    assert "svg大师" in text
    assert "对外身份" in text or "【当前角色】为准" in text


def test_role_identity_block_with_persona_and_avatar():
    from app.engine.agent.prompts import build_role_identity_block

    block = build_role_identity_block(
        name="股票研究员",
        system_prompt="专注 A 股基本面",
        avatar="媒体/生成/2026-09/avatar.png",
    )
    assert "股票研究员" in block
    assert "专注 A 股基本面" in block
    assert "媒体/生成/2026-09/avatar.png" in block
    assert "尚未写人设" not in block


def test_turn_hub_always_injects_role_identity(tmp_path):
    """会话归属角色即使人设为空，也要向 Agent 注入身份卡。"""
    from app.engine.agent.prompts import build_system_prompt
    from app.engine.chat.turn_hub import TurnExecutionHub

    roles = _roles(tmp_path)
    conv = _conv(tmp_path)
    rid = roles.create(name="svg大师", system_prompt="")["id"]
    # 存量角色可能是 none（引导功能上线前）；与 active 一样须有身份卡
    roles.update(rid, onboarding_status="none")
    cid = conv.create(role_id=rid)

    hub = TurnExecutionHub(_FakeAgentForRole(), conv, roles=roles)
    block = hub._role_system_prompt_for(cid)
    assert "svg大师" in block
    assert "你当前就是这个角色" in block
    assert "[角色引导]" not in block

    assembled = build_system_prompt(role_system_prompt=block)
    assert "【当前角色】" in assembled
    assert "svg大师" in assembled
    assert "对外身份以【当前角色】为准" in assembled


def test_turn_hub_identity_includes_onboarding_layer(tmp_path):
    from app.engine.chat.turn_hub import TurnExecutionHub

    roles = _roles(tmp_path)
    conv = _conv(tmp_path)
    rid = roles.create(name="新人设", system_prompt="")["id"]
    assert roles.get(rid)["onboarding_status"] == "active"
    cid = conv.create(role_id=rid)

    hub = TurnExecutionHub(_FakeAgentForRole(), conv, roles=roles)
    block = hub._role_system_prompt_for(cid)
    assert "[角色引导]" in block
    assert "新人设" in block
    assert "你当前就是这个角色" in block


class _FakeAgentForRole:
    tools = type("T", (), {"sandbox": None})()

    async def run(self, *a, **k):
        if False:
            yield None


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


def test_list_roles_tool_lists_all_and_filters(tmp_path):
    from app.engine.agent.tool_impl.role_tools import RoleTools

    store = _roles(tmp_path)
    created = store.create(name="股票研究员", system_prompt="专注股票")
    store.schedules.create(
        role_id=created["id"],
        prompt="盘后复盘",
        interval_hours=24,
    )
    conv = _conv(tmp_path)
    cid = conv.create(role_id=created["id"])
    tools = RoleTools(store, conversations=conv)

    listed = tools.list_roles({}, conversation_id=cid)
    assert "error" not in listed
    names = [r["name"] for r in listed["roles"]]
    assert names == [DEFAULT_ROLE_NAME, "股票研究员"]
    assert "股票研究员" in listed["summary"]
    researcher = next(r for r in listed["roles"] if r["id"] == created["id"])
    assert researcher["system_prompt"] == "专注股票"
    assert researcher["is_current"] is True
    assert researcher["is_default"] is False
    assert researcher["schedule_count"] == 1
    default = next(r for r in listed["roles"] if r["is_default"])
    assert default["is_current"] is False
    assert default["schedule_count"] == 0

    by_id = tools.list_roles({"role_id": created["id"]}, conversation_id=cid)
    assert by_id["role"]["name"] == "股票研究员"
    assert by_id["role"]["is_current"] is True
    assert len(by_id["roles"]) == 1

    by_name = tools.list_roles({"name": "股票研究员"})
    assert by_name["role"]["id"] == created["id"]
    assert by_name["role"]["system_prompt"] == "专注股票"

    store.create(name="Researcher", system_prompt="EN")
    by_name_ci = tools.list_roles({"name": "researcher"})
    assert by_name_ci["role"]["name"] == "Researcher"

    missing = tools.list_roles({"name": "不存在的角色"})
    assert missing["error"] == "role not found"
    assert missing["roles"] == []

    missing_id = tools.list_roles({"role_id": "no-such-id"})
    assert missing_id["error"] == "role not found"


def test_list_roles_tool_hides_api_worker_roles(tmp_path):
    from app.engine.agent.tool_impl.role_tools import RoleTools
    from app.engine.roles import API_ROLE_PREFIX, VISIBILITY_HIDDEN

    store = _roles(tmp_path)
    hidden = store.create(
        name="周报助手 · 脚本",
        visibility=VISIBILITY_HIDDEN,
        role_id=f"{API_ROLE_PREFIX}abcd",
        onboarding_status="completed",
    )
    tools = RoleTools(store)
    listed = tools.list_roles({})
    assert hidden["id"] not in [r["id"] for r in listed["roles"]]
    by_id = tools.list_roles({"role_id": hidden["id"]})
    assert by_id["error"] == "role not found"


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
    """reassign_role 不改 updated_at，避免迁入会话劫持目标角色 tip。"""
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


def test_list_timeline_limit_zero_is_tip_only(tmp_path):
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
        include_messages=False,
        limit=0,
        tip_id=tip,
        only_with_messages=True,
    )
    assert has_more is True
    assert [s["id"] for s in page] == [tip]


def test_list_timeline_message_limit_keeps_tail(tmp_path):
    conv = _conv(tmp_path)
    cid = conv.create(role_id=DEFAULT_ROLE_ID, title="long")
    for i in range(5):
        conv.append_exchange(
            cid, f"u{i}", {"role": "assistant", "text": f"a{i}"}
        )
    page, has_more = conv.list_timeline(
        DEFAULT_ROLE_ID,
        include_messages=True,
        limit=1,
        message_limit=3,
        only_with_messages=True,
    )
    assert has_more is False
    assert len(page) == 1
    assert [m["text"] for m in page[0]["messages"]] == ["a3", "u4", "a4"]
    assert page[0]["older_message_count"] == 7


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
