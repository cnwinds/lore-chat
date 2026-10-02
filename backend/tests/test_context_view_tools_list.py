"""ContextViewTools.list"""

from __future__ import annotations

import pytest

from tests.test_context_view_tools_common import cv_env  # noqa: F401


def test_list_root_owner(cv_env):
    out = cv_env.tools.list({})
    names = {e["name"] for e in out.get("entries", [])}
    assert "kb" in names
    assert "conversations" in names
    assert "memory" in names


def test_list_kb_dir_kinds_protected_binary(cv_env):
    cv_env.repo.write_doc(
        "列/文档.md",
        {"title": "列标题", "tags": [], "source": "t"},
        "# b\n",
        commit_msg="t",
    )
    cv_env.repo.write_bytes("列/图.png", b"png", commit_msg="t")
    cv_env.repo.write_bytes("系统/受保护.md", b"x", commit_msg="t")
    out = cv_env.tools.list({"uri": "lore://kb/列/"})
    by_name = {e["name"]: e for e in out.get("entries", [])}
    assert by_name["文档.md"]["type"] == "doc"
    assert by_name["文档.md"].get("title") == "列标题"
    assert by_name["图.png"]["type"] == "binary"


def test_list_200_cap_cursor(cv_env):
    for i in range(210):
        cv_env.repo.write_bytes(f"大量/f{i}.txt", b"x", commit_msg="t")
    first = cv_env.tools.list({"uri": "lore://kb/大量/", "depth": 1})
    assert len(first.get("entries", [])) == 200
    assert first.get("next_cursor")
    second = cv_env.tools.list(
        {
            "uri": "lore://kb/大量/",
            "cursor": first["next_cursor"],
        }
    )
    assert len(second.get("entries", [])) >= 10


def test_list_dm_roles_with_counts(cv_env):
    rid = cv_env.roles.create(name="计数角色", system_prompt="")["id"]
    cv_env.conv.create(role_id=rid)
    cv_env.conv.create(role_id=rid)
    out = cv_env.tools.list({"uri": "lore://conversations/dm/"})
    assert any(e.get("conversation_count", 0) >= 2 for e in out.get("entries", []))


def test_list_dm_role_ordered_by_activity(cv_env):
    rid = cv_env.roles.create(name="排序", system_prompt="")["id"]
    old = cv_env.conv.create(role_id=rid)
    new = cv_env.conv.create(role_id=rid)
    cv_env.conv.conn.execute(
        "UPDATE conversations SET updated_at = ?, last_user_message_at = ? WHERE id = ?",
        ("2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00", old),
    )
    cv_env.conv.conn.execute(
        "UPDATE conversations SET updated_at = ?, last_user_message_at = ? WHERE id = ?",
        ("2026-06-01T00:00:00+00:00", "2026-06-01T00:00:00+00:00", new),
    )
    cv_env.conv.conn.commit()
    t = cv_env.conv.begin_turn(new, user_text="hi", client_message_id="u1")
    cv_env.conv.finalize_turn(
        new,
        t["turn_id"],
        assistant={"text": "ok", "timeline": [], "sources": [], "status": "complete"},
    )
    out = cv_env.tools.list({"uri": f"lore://conversations/dm/{rid}/"})
    entries = out.get("entries") or []
    assert entries[0]["name"] == new


def test_list_rooms(cv_env):
    ra = cv_env.roles.create(name="A", system_prompt="")["id"]
    rb = cv_env.roles.create(name="B", system_prompt="")["id"]
    cid = cv_env.conv.rooms.find_or_create_peer_dm(ra, rb, title="互通")
    out = cv_env.tools.list({"uri": "lore://conversations/rooms/"})
    assert any(e.get("name") == cid for e in out.get("entries", []))


def test_list_memory_root_owner_kinds_items(cv_env):
    cv_env.owner.remember("列表记忆项", origin="explicit_remember")
    fact = cv_env.owner.store.list_confirmed()[0]
    kind = fact.get("category") or "preference"
    root = cv_env.tools.list({"uri": "lore://memory/"})
    assert any(e["name"] == "owner" for e in root.get("entries", []))
    kinds = cv_env.tools.list({"uri": "lore://memory/owner/"})
    assert any(e.get("count", 0) >= 1 for e in kinds.get("entries", []))
    items = cv_env.tools.list({"uri": f"lore://memory/owner/{kind}/"})
    assert any(e.get("preview") for e in items.get("entries", []))


def test_list_memory_role_roles(cv_env):
    cv_env.roles.create(name="角色A", system_prompt="")
    out = cv_env.tools.list({"uri": "lore://memory/role/"})
    assert len(out.get("entries", [])) >= 1


def test_list_conversation_uri_errors(cv_env):
    cid = cv_env.conv.create(role_id="default")
    out = cv_env.tools.list({"uri": f"lore://conversations/dm/default/{cid}/"})
    assert out.get("error") == "use_read"


def test_channel_list_root_and_conversations(cv_env):
    role = cv_env.roles.create(name="通道用", system_prompt="")
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
    root = cv_env.tools.list({}, conversation_id=cid)
    assert "kb" in {e["name"] for e in root.get("entries", [])}
    convs = cv_env.tools.list({"uri": "lore://conversations/"}, conversation_id=cid)
    entries = convs.get("entries") or []
    assert len(entries) == 1
    assert entries[0]["type"] == "conversation"
    assert entries[0]["uri"].endswith(f"/{cid}/")
    read_back = cv_env.tools.read({"uri": entries[0]["uri"]}, conversation_id=cid)
    assert read_back.get("messages") is not None
    assert read_back.get("error") != "out_of_scope"
