"""memory/role 与 memory/persona 目录检索与列举。"""

from __future__ import annotations

import pytest

from app.engine.context_view.compile import compile_search
from app.engine.context_view.errors import OutOfScope
from tests.test_context_view_tools_common import cv_env  # noqa: F401


def ViewScope_build(cv_env, *, cid=None, role_id=None):
    from app.engine.context_view.scope import ViewScope

    return ViewScope.build(
        conversations=cv_env.conv,
        roles=cv_env.roles,
        cards=cv_env.cards,
        channel_instances=cv_env.channel_instances,
        conversation_id=cid,
        responding_role_id=role_id,
    )


def test_owner_search_memory_role_dir_expands(cv_env):
    rid = cv_env.roles.create(name="R1", system_prompt="")["id"]
    plan = compile_search(
        ViewScope_build(cv_env),
        ["lore://memory/role/"],
    )
    keys = {t[0] for t in plan.memory_targets}
    assert f"role:{rid}" in keys


def test_owner_search_memory_persona_dir(cv_env):
    pid = cv_env.roles.create_persona(name="P1", system_prompt="")["id"]
    plan = compile_search(
        ViewScope_build(cv_env),
        ["lore://memory/persona/"],
    )
    keys = {t[0] for t in plan.memory_targets}
    assert f"persona:{pid}" in keys


def test_owner_search_role_kind_path(cv_env):
    rid = cv_env.roles.create(name="R2", system_prompt="")["id"]
    plan = compile_search(
        ViewScope_build(cv_env),
        [f"lore://memory/role/{rid}/practice/"],
    )
    assert plan.memory_targets == [(f"role:{rid}", "practice")]


def test_owner_list_memory_persona_dir(cv_env):
    cv_env.roles.create_persona(name="P2", system_prompt="")
    out = cv_env.tools.list({"uri": "lore://memory/persona/"})
    assert out.get("error") != "out_of_scope"
    assert len(out.get("entries", [])) >= 1


def test_channel_memory_role_out_of_scope(cv_env):
    role, iid, cid = _channel(cv_env)
    with pytest.raises(OutOfScope):
        ViewScope_build(cv_env, cid=cid, role_id=role).resolve_and_check(
            "lore://memory/role/"
        )
    out = cv_env.tools.search(
        {"query": "x", "paths": ["lore://memory/role/"]},
        conversation_id=cid,
    )
    assert out.get("error") == "out_of_scope"


def test_owner_list_persona_root_empty_when_no_personas(cv_env):
    out = cv_env.tools.list({"uri": "lore://memory/persona/"})
    assert out.get("error") is None
    assert out.get("entries") == []


def test_owner_search_persona_root_empty_when_no_personas(cv_env):
    out = cv_env.tools.search(
        {"query": "x", "paths": ["lore://memory/persona/"]},
    )
    assert out.get("error") is None
    assert out.get("memory", []) == []


def test_channel_persona_root_out_of_scope_without_persona(cv_env, monkeypatch):
    role, iid, cid = _channel(cv_env)
    monkeypatch.setattr(
        "app.engine.context_view.scope.ViewScope._persona_id_for_instance",
        staticmethod(lambda store, inst_id: None),
    )
    out = cv_env.tools.list({"uri": "lore://memory/persona/"}, conversation_id=cid)
    assert out.get("error") == "out_of_scope"
    sr = cv_env.tools.search(
        {"query": "x", "paths": ["lore://memory/persona/"]},
        conversation_id=cid,
    )
    assert sr.get("error") == "out_of_scope"


def test_channel_memory_persona_own_only(cv_env):
    role, iid, cid, persona_id = _channel_with_persona(cv_env)
    plan = compile_search(
        ViewScope_build(cv_env, cid=cid, role_id=role),
        ["lore://memory/persona/"],
    )
    keys = {t[0] for t in plan.memory_targets}
    assert keys == {f"persona:{persona_id}"}
    listed = cv_env.tools.list({"uri": "lore://memory/persona/"}, conversation_id=cid)
    names = {e["name"] for e in listed.get("entries", [])}
    assert names == {persona_id}


def _channel(cv_env):
    role = cv_env.roles.create(name="通道", system_prompt="")
    persona = cv_env.roles.create_persona(name="P", system_prompt="")
    inst = cv_env.channel_instances.create(
        type_id="script_api",
        name="ch",
        persona_id=persona["id"],
        role_id=role["id"],
    )
    cid = cv_env.conv.create(
        role_id=role["id"],
        origin="api",
        channel_instance_id=inst["id"],
    )
    return role["id"], inst["id"], cid


def _channel_with_persona(cv_env):
    role, iid, cid = _channel(cv_env)
    scope = ViewScope_build(cv_env, cid=cid, role_id=role)
    pid = scope.channel_persona_id
    assert pid
    return role, iid, cid, pid
