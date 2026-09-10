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
