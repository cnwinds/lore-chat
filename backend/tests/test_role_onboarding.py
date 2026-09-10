"""测试角色引导与配置工具。"""

import tempfile
from pathlib import Path

import pytest

from app.engine.roles import RoleStore


@pytest.fixture
def role_store():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield RoleStore(Path(tmpdir) / "roles")


def test_onboarding_status_migration(role_store):
    """测试 onboarding_status 迁移逻辑。"""
    roles = role_store.list_all()
    assert len(roles) > 0
    default_role = roles[0]
    assert default_role["is_default"] is True
    assert "onboarding_status" in default_role


def test_create_role_with_onboarding(role_store):
    """测试创建角色时的 onboarding_status 设置。"""
    role1 = role_store.create(name="测试角色1")
    assert role1["onboarding_status"] == "active"
    assert role1["system_prompt"] == ""

    role2 = role_store.create(name="测试角色2", system_prompt="我是测试角色")
    assert role2["onboarding_status"] == "completed"
    assert role2["system_prompt"] == "我是测试角色"


def test_update_role_onboarding_status(role_store):
    """测试更新角色 onboarding_status。"""
    role = role_store.create(name="测试角色")
    assert role["onboarding_status"] == "active"

    updated = role_store.update(
        role["id"],
        system_prompt="完成了",
        onboarding_status="completed",
    )
    assert updated["onboarding_status"] == "completed"
    assert updated["system_prompt"] == "完成了"


def test_skip_onboarding(role_store):
    """测试跳过引导。"""
    role = role_store.create(name="测试角色")
    skipped = role_store.update(role["id"], onboarding_status="skipped")
    assert skipped["onboarding_status"] == "skipped"


def test_create_and_list_schedules(role_store):
    """测试创建和列出定时任务。"""
    role = role_store.create(name="测试角色")
    schedules = role_store.schedules.list_for_role(role["id"])
    assert len(schedules) == 0

    s1 = role_store.schedules.create(
        role["id"],
        prompt="每日总结",
        interval_hours=24,
    )
    assert s1["prompt"] == "每日总结"
    assert s1["interval_hours"] == 24
    assert s1["enabled"] is True

    schedules = role_store.schedules.list_for_role(role["id"])
    assert len(schedules) == 1


def test_update_schedule(role_store):
    """测试更新定时任务。"""
    role = role_store.create(name="测试角色")
    s = role_store.schedules.create(
        role["id"],
        prompt="原提示",
        interval_hours=24,
    )
    updated = role_store.schedules.update(
        s["id"],
        prompt="新提示",
        interval_hours=12,
        enabled=False,
    )
    assert updated["prompt"] == "新提示"
    assert updated["interval_hours"] == 12
    assert updated["enabled"] is False


def test_delete_schedule(role_store):
    """测试删除定时任务。"""
    role = role_store.create(name="测试角色")
    s = role_store.schedules.create(
        role["id"],
        prompt="测试",
        interval_hours=24,
    )
    role_store.schedules.delete(s["id"])
    schedules = role_store.schedules.list_for_role(role["id"])
    assert len(schedules) == 0


def test_role_tools_integration():
    """测试 RoleTools 与 RoleStore 集成。"""
    from app.engine.agent.tool_impl.role_tools import RoleTools

    with tempfile.TemporaryDirectory() as tmpdir:
        store = RoleStore(Path(tmpdir) / "roles")
        tools = RoleTools(store, conversations=None)

        result = tools.create_role({"name": "测试工具角色"})
        assert "role" in result
        assert result["role"]["name"] == "测试工具角色"

        role_id = result["role"]["id"]

        update_result = tools.update_role(
            {"role_id": role_id, "name": "新名称"},
            conversation_id=None,
        )
        assert "role" in update_result
        assert update_result["role"]["name"] == "新名称"

        list_result = tools.list_role_schedules(
            {"role_id": role_id},
            conversation_id=None,
        )
        assert "schedules" in list_result
        assert len(list_result["schedules"]) == 0

        create_result = tools.create_role_schedule(
            {
                "role_id": role_id,
                "prompt": "测试定时",
                "interval_hours": 6,
            },
            conversation_id=None,
        )
        assert "schedule" in create_result

        finalize_result = tools.finalize_role_onboarding(
            {
                "role_id": role_id,
                "system_prompt": "最终人设",
                "schedules": [
                    {"prompt": "每日总结", "interval_hours": 24},
                ],
            },
            conversation_id=None,
        )
        assert "role" in finalize_result
        assert finalize_result["role"]["system_prompt"] == "最终人设"
        assert finalize_result["role"]["onboarding_status"] == "completed"
        assert len(finalize_result["schedules"]) == 1


def _stub_kickoff(client, monkeypatch):
    calls: list[dict] = []

    def fake(**kwargs):
        calls.append(kwargs)
        return {"turn_id": "kickoff-turn", "status": "running"}

    monkeypatch.setattr(
        client.app.state.container.chat_runner,
        "begin_persisted_turn",
        fake,
    )
    return calls


def test_create_role_without_prompt_kicks_off(client, monkeypatch):
    calls = _stub_kickoff(client, monkeypatch)
    r = client.post("/api/roles", json={"name": "股票研究院"})
    assert r.status_code == 200
    body = r.json()
    assert body["onboarding_status"] == "active"
    assert len(calls) == 1
    assert calls[0]["client_message_id"] == f"onboarding-kickoff:{body['id']}"
    assert calls[0]["observation_allowed"] is False
    assert "这个角色刚创建" in calls[0]["user_text"]
    assert calls[0]["web_enabled"] is False


def test_create_role_with_prompt_skips_kickoff(client, monkeypatch):
    calls = _stub_kickoff(client, monkeypatch)
    r = client.post(
        "/api/roles",
        json={"name": "已有人设", "system_prompt": "专注新闻"},
    )
    assert r.status_code == 200
    assert r.json()["onboarding_status"] == "completed"
    assert calls == []


def test_create_role_succeeds_when_kickoff_fails(client, monkeypatch):
    def boom(**_kwargs):
        raise RuntimeError("llm down")

    monkeypatch.setattr(
        client.app.state.container.chat_runner,
        "begin_persisted_turn",
        boom,
    )
    r = client.post("/api/roles", json={"name": "仍能建"})
    assert r.status_code == 200
    assert r.json()["onboarding_status"] == "active"


def test_default_role_ensure_active_skips_kickoff(client, monkeypatch):
    calls = _stub_kickoff(client, monkeypatch)
    r = client.post("/api/roles/default/ensure-active")
    assert r.status_code == 200
    assert calls == []


def test_ensure_active_kicks_off_existing_active_role(client, monkeypatch):
    role = client.app.state.container.roles.create(name="旧角色")
    calls = _stub_kickoff(client, monkeypatch)
    r = client.post(f"/api/roles/{role['id']}/ensure-active")
    assert r.status_code == 200
    assert len(calls) == 1
    assert calls[0]["client_message_id"] == f"onboarding-kickoff:{role['id']}"
    assert calls[0]["conversation_id"] == r.json()["conversation_id"]


def test_timeline_first_page_kicks_off(client, monkeypatch):
    role = client.app.state.container.roles.create(name="时间线引导")
    calls = _stub_kickoff(client, monkeypatch)
    r = client.get(f"/api/roles/{role['id']}/timeline")
    assert r.status_code == 200
    assert len(calls) == 1


def test_timeline_older_page_skips_kickoff(client, monkeypatch):
    role = client.app.state.container.roles.create(name="续载不引导")
    calls = _stub_kickoff(client, monkeypatch)
    r = client.get(
        f"/api/roles/{role['id']}/timeline",
        params={"before_created_at": "2020-01-01T00:00:00+00:00", "before_id": "x"},
    )
    assert r.status_code == 200
    assert calls == []


def test_maybe_kickoff_skips_when_user_already_spoke(tmp_path):
    from types import SimpleNamespace

    from app.engine.conversations import ConversationStore
    from app.engine.role_onboarding import maybe_kickoff_role_onboarding
    from app.engine.roles import RoleStore

    roles = RoleStore(tmp_path / "roles")
    conversations = ConversationStore(tmp_path / "conversations")
    role = roles.create(name="已开口")
    cid, _ = conversations.ensure_active_conversation(role["id"], idle_hours=6)
    turn = conversations.begin_turn(
        cid, "你好，先做行情复盘", "real-1", observation_allowed=False
    )
    conversations.finalize_turn(
        cid,
        turn["turn_id"],
        {
            "text": "好的",
            "timeline": [],
            "sources": [],
            "status": "complete",
        },
    )
    calls: list[dict] = []

    class Runner:
        def begin_persisted_turn(self, **kwargs):
            calls.append(kwargs)
            return kwargs

    container = SimpleNamespace(
        roles=roles,
        conversations=conversations,
        chat_runner=Runner(),
        settings=SimpleNamespace(continuity_idle_hours=6),
    )
    assert maybe_kickoff_role_onboarding(container, role["id"]) is None
    assert calls == []


def test_maybe_kickoff_skips_default_role(tmp_path):
    from types import SimpleNamespace

    from app.engine.conversations import ConversationStore
    from app.engine.role_onboarding import maybe_kickoff_role_onboarding
    from app.engine.roles import DEFAULT_ROLE_ID, RoleStore

    roles = RoleStore(tmp_path / "roles")
    conversations = ConversationStore(tmp_path / "conversations")
    calls: list[dict] = []

    class Runner:
        def begin_persisted_turn(self, **kwargs):
            calls.append(kwargs)
            return kwargs

    container = SimpleNamespace(
        roles=roles,
        conversations=conversations,
        chat_runner=Runner(),
        settings=SimpleNamespace(continuity_idle_hours=6),
    )
    assert maybe_kickoff_role_onboarding(container, DEFAULT_ROLE_ID) is None
    assert calls == []


def test_onboarding_kickoff_does_not_rename_or_index(tmp_path):
    from app.engine.conversations import ConversationStore

    store = ConversationStore(tmp_path / "conversations")
    cid = store.create()
    store.begin_turn(
        cid,
        "（系统）这个角色刚创建。",
        "onboarding-kickoff:role-1",
        observation_allowed=False,
    )
    assert store.get(cid)["title"] == "新对话"
    kinds = [
        r[0]
        for r in store.conn.execute(
            "SELECT kind FROM derivation_outbox WHERE status='pending' ORDER BY kind"
        ).fetchall()
    ]
    assert "index_fts" not in kinds
    assert "index_vector" not in kinds
