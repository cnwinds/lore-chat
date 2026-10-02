"""read 一次读多个地址。"""

from __future__ import annotations

import pytest

from app.engine.agent.skill_activation import activated_skill_roots
from app.engine.disclosure import DisclosureWindows
from tests.test_context_view_tools_common import cv_env  # noqa: F401


def test_read_batch_three_docs_marks_all_read(cv_env):
    for i in range(3):
        cv_env.repo.write_doc(
            f"批/文{i}.md",
            {"title": f"D{i}", "tags": [], "source": "t"},
            f"# body{i}\n",
            commit_msg="t",
        )
    cid = cv_env.conv.create(role_id="default")
    out = cv_env.tools.read(
        {
            "uris": [
                "lore://kb/批/文0.md",
                "lore://kb/批/文1.md",
                "lore://kb/批/文2.md",
            ]
        },
        conversation_id=cid,
    )
    assert out.get("error") is None
    assert len(out.get("items", [])) == 3
    assert all(it.get("body") for it in out["items"])
    src_paths = {s.get("path") for s in out.get("sources", [])}
    assert src_paths == {"批/文0.md", "批/文1.md", "批/文2.md"}
    for p in src_paths:
        assert cv_env.tools.read_guard.is_read(cid, p)


def test_read_batch_items_carry_canonical_uri(cv_env):
    cv_env.repo.write_bytes("批/a.txt", b"a", commit_msg="t")
    cv_env.repo.write_bytes("批/b.txt", b"b", commit_msg="t")
    out = cv_env.tools.read({"uris": ["批/a.txt", "lore://kb/批/b.txt/", "批/"]})
    by_uri = {it["uri"]: it for it in out["items"]}
    assert by_uri["lore://kb/批/a.txt"].get("body") == "a"
    assert by_uri["lore://kb/批/b.txt"].get("body") == "b"
    assert by_uri["lore://kb/批/"].get("error") == "is_directory"


def test_read_batch_out_of_scope_aborts_all(cv_env):
    cv_env.repo.write_doc(
        "批/好.md",
        {"title": "ok", "tags": [], "source": "t"},
        "# ok",
        commit_msg="t",
    )
    role = cv_env.roles.create(name="通道", system_prompt="")
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
    out = cv_env.tools.read(
        {
            "uris": [
                "lore://kb/批/好.md",
                f"lore://conversations/channels/{inst['id']}/{cid_b}/",
            ]
        },
        conversation_id=cid_a,
    )
    assert out.get("error") == "out_of_scope"
    assert not cv_env.tools.read_guard.is_read(cid_a, "批/好.md")


def test_read_batch_partial_item_errors(cv_env):
    cv_env.repo.write_doc(
        "批/存在.md",
        {"title": "e", "tags": [], "source": "t"},
        "# e",
        commit_msg="t",
    )
    out = cv_env.tools.read(
        {
            "uris": [
                "lore://kb/批/存在.md",
                "lore://kb/批/无.md",
                "lore://kb/批/",
            ]
        }
    )
    assert out.get("error") is None
    by_uri = {it["uri"]: it for it in out.get("items", [])}
    assert by_uri["lore://kb/批/存在.md"].get("body")
    assert by_uri["lore://kb/批/无.md"].get("error") == "not_found"
    assert by_uri["lore://kb/批/"].get("error") == "is_directory"


def test_read_batch_budget_cap(cv_env):
    big = "x" * 12000
    uris = []
    for i in range(4):
        p = f"预算/大{i}.md"
        cv_env.repo.write_doc(
            p,
            {"title": "b", "tags": [], "source": "t"},
            big,
            commit_msg="t",
        )
        uris.append(f"lore://kb/{p}")
    windows = DisclosureWindows(deep=16000, max_chars=32000)
    cv_env.tools.disclosure = windows
    out = cv_env.tools.read({"uris": uris, "intent": "deep"})
    total = sum(
        len(it.get("body") or "")
        for it in out.get("items", [])
        if not it.get("error") and not it.get("skipped_budget")
    )
    assert total <= windows.max_chars
    assert any(
        it.get("next_offset") or it.get("skipped_budget")
        for it in out.get("items", [])
    )


def test_read_batch_max_eight_skipped(cv_env):
    uris = []
    for i in range(10):
        p = f"八/文{i}.md"
        cv_env.repo.write_doc(
            p,
            {"title": "t", "tags": [], "source": "t"},
            "# x",
            commit_msg="t",
        )
        uris.append(f"lore://kb/{p}")
    out = cv_env.tools.read({"uris": uris})
    assert len(out.get("items", [])) == 8
    assert len(out.get("skipped", [])) == 2


def test_read_single_uri_structure_unchanged(cv_env):
    cv_env.repo.write_doc(
        "单/读.md",
        {"title": "单", "tags": [], "source": "t"},
        "# one",
        commit_msg="t",
    )
    single = cv_env.tools.read({"uri": "lore://kb/单/读.md"})
    batch = cv_env.tools.read({"uris": ["lore://kb/单/读.md"]})
    assert batch.get("items") is None
    for key in ("summary", "body", "sources", "uri", "kind", "total_chars", "offset"):
        assert key in single
        assert single[key] == batch.get(key) or key == "summary"


def test_read_missing_uri_params(cv_env):
    out = cv_env.tools.read({})
    assert out.get("error") == "invalid_uri"


def test_read_batch_spot_three_long_docs(cv_env):
    body = "z" * 10000
    uris = []
    for i in range(3):
        p = f"窗/spot{i}.md"
        cv_env.repo.write_doc(
            p,
            {"title": "t", "tags": [], "source": "t"},
            body,
            commit_msg="t",
        )
        uris.append(f"lore://kb/{p}")
    spot = cv_env.tools.disclosure.spot
    out = cv_env.tools.read({"uris": uris, "intent": "spot"})
    for it in out["items"]:
        assert it.get("body")
        assert it.get("returned_chars", 0) <= spot
        assert it.get("next_offset") is not None


def test_read_batch_deep_budget_three_docs(cv_env):
    body = "y" * 20000
    uris = []
    for i in range(3):
        p = f"窗/deep{i}.md"
        cv_env.repo.write_doc(
            p,
            {"title": "t", "tags": [], "source": "t"},
            body,
            commit_msg="t",
        )
        uris.append(f"lore://kb/{p}")
    windows = DisclosureWindows(deep=16000, max_chars=32000)
    cv_env.tools.disclosure = windows
    out = cv_env.tools.read({"uris": uris, "intent": "deep"})
    items = out["items"]
    assert items[0].get("returned_chars", 0) <= windows.deep
    assert items[1].get("returned_chars", 0) <= windows.max_chars - items[0].get(
        "returned_chars", 0
    )
    assert items[2].get("skipped_budget") is True
    total = sum(len(it.get("body") or "") for it in items[:2])
    assert total <= windows.max_chars


def test_read_batch_next_offset_matches_single_read(cv_env):
    body = "q" * 8000
    cv_env.repo.write_doc(
        "窗/一致.md",
        {"title": "t", "tags": [], "source": "t"},
        body,
        commit_msg="t",
    )
    uri = "lore://kb/窗/一致.md"
    single = cv_env.tools.read({"uri": uri, "intent": "spot"})
    batch = cv_env.tools.read({"uris": [uri], "intent": "spot"})
    assert batch.get("items") is None
    assert single.get("next_offset") == batch.get("next_offset")
    assert single.get("returned_chars") == batch.get("returned_chars")


def test_skill_activation_two_skills_one_read(cv_env):
    catalog = [
        {"root": "技能/a", "name": "A", "description": ""},
        {"root": "技能/b", "name": "B", "description": ""},
    ]
    conv = {
        "messages": [
            {
                "role": "assistant",
                "timeline": [
                    {
                        "type": "tool",
                        "tool": "read",
                        "status": "done",
                        "sources": [
                            {"type": "kb", "path": "技能/a/SKILL.md"},
                            {"type": "kb", "path": "技能/b/SKILL.md"},
                        ],
                    }
                ],
            }
        ]
    }
    roots = activated_skill_roots(conv, catalog)
    assert roots == ["技能/a", "技能/b"]
