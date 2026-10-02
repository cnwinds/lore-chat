"""通道与会话可见性回归：禁止跨来访者泄露。"""

from __future__ import annotations

import pytest

from app.engine.context_view.compile import compile_search
from app.engine.context_view.errors import OutOfScope
from app.engine.context_view.scope import ViewScope
from app.index.message_chunk import MessageChunk

def _channel_scope(cv_env, *, cid: str, role_id: str, inst_id: str):
    return ViewScope.build(
        conversations=cv_env.conv,
        roles=cv_env.roles,
        cards=cv_env.cards,
        channel_instances=cv_env.channel_instances,
        conversation_id=cid,
        responding_role_id=role_id,
    )


def _two_visitor_channel(cv_env):
    role = cv_env.roles.create(name="通道用", system_prompt="")
    persona = cv_env.roles.create_persona(name="P", system_prompt="")
    inst = cv_env.channel_instances.create(
        type_id="script_api",
        name="ch",
        persona_id=persona["id"],
        role_id=role["id"],
    )
    cid_a = cv_env.conv.create(
        role_id=role["id"],
        origin="api",
        channel_instance_id=inst["id"],
    )
    cid_b = cv_env.conv.create(
        role_id=role["id"],
        origin="api",
        channel_instance_id=inst["id"],
    )
    cv_env.ci.upsert_message_chunks(
        conversation_id=cid_a,
        message_id="ma",
        role="user",
        ts="2026-07-10T10:00:00",
        conversation_title="A",
        chunks=[MessageChunk(0, 0, 8, "secret_a")],
    )
    cv_env.ci.upsert_message_chunks(
        conversation_id=cid_b,
        message_id="mb",
        role="user",
        ts="2026-07-10T10:00:00",
        conversation_title="B",
        chunks=[MessageChunk(0, 0, 8, "secret_b")],
    )
    return role["id"], inst["id"], cid_a, cid_b


def test_channel_compile_never_lists_sibling_conversations(cv_env):
    rid, iid, cid_a, cid_b = _two_visitor_channel(cv_env)
    scope = _channel_scope(cv_env, cid=cid_a, role_id=rid, inst_id=iid)
    with pytest.raises(OutOfScope):
        scope.resolve_and_check(f"lore://conversations/channels/{iid}/")
    with pytest.raises(OutOfScope):
        scope.resolve_and_check(f"lore://conversations/channels/{iid}/{cid_b}/")
    with pytest.raises(OutOfScope):
        scope.resolve_and_check(f"conversation://{cid_b}")
    with pytest.raises(OutOfScope):
        scope.resolve_and_check("lore://conversations/dm/")
    with pytest.raises(OutOfScope):
        scope.resolve_and_check("lore://conversations/rooms/")

    plan = compile_search(scope, ["lore://conversations/"])
    assert set(plan.conversation_ids).issubset({cid_a})


def test_channel_tools_no_cross_visitor_hits(cv_env):
    rid, iid, cid_a, cid_b = _two_visitor_channel(cv_env)
    out = cv_env.tools.search(
        {
            "query": "secret_b",
            "paths": [f"lore://conversations/channels/{iid}/"],
        },
        conversation_id=cid_a,
    )
    assert out.get("error") in (None, "out_of_scope") or not any(
        s.get("cid") == cid_b for s in out.get("sources", [])
    )
    if out.get("error") is None:
        assert not any(s.get("cid") == cid_b for s in out.get("sources", []))

    read_other = cv_env.tools.read(
        {"uri": f"lore://conversations/channels/{iid}/{cid_b}/"},
        conversation_id=cid_a,
    )
    assert read_other.get("error") == "out_of_scope"

    listed = cv_env.tools.list({"uri": "lore://conversations/"}, conversation_id=cid_a)
    cids = {e.get("name") for e in listed.get("entries", []) if e.get("type") == "conversation"}
    assert cid_b not in cids
    assert cid_a in cids or len(cids) <= 1


def test_owner_never_compiles_channel_conversations(cv_env):
    rid, iid, cid_a, _cid_b = _two_visitor_channel(cv_env)
    owner_cid = cv_env.conv.create(role_id="default")
    scope = ViewScope.build(
        conversations=cv_env.conv,
        roles=cv_env.roles,
        cards=cv_env.cards,
        channel_instances=cv_env.channel_instances,
        conversation_id=owner_cid,
    )
    for p in [
        "lore://conversations/",
        "lore://conversations/dm/",
        "lore://conversations/rooms/",
    ]:
        plan = compile_search(scope, [p])
        assert cid_a not in plan.conversation_ids
    with pytest.raises(OutOfScope):
        scope.resolve_and_check(f"lore://conversations/channels/{iid}/")


def test_channel_memory_root_no_owner_or_role_targets(cv_env):
    rid, iid, cid_a, _ = _two_visitor_channel(cv_env)
    scope = _channel_scope(cv_env, cid=cid_a, role_id=rid, inst_id=iid)
    plan = compile_search(scope, ["lore://memory/"])
    keys = {t[0] for t in plan.memory_targets}
    assert "owner" not in keys
    assert not any(k.startswith("role:") for k in keys)
