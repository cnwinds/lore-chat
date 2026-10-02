"""list 灵活展开、筛选与单项列举。"""

from __future__ import annotations

import pytest

from tests.test_context_view_tools_common import cv_env  # noqa: F401


def test_list_depth1_pagination_unchanged(cv_env):
    for i in range(210):
        cv_env.repo.write_bytes(f"大量/f{i}.txt", b"x", commit_msg="t")
    first = cv_env.tools.list({"uri": "lore://kb/大量/", "depth": 1})
    assert len(first.get("entries", [])) == 200
    assert first.get("next_cursor")
    second = cv_env.tools.list(
        {"uri": "lore://kb/大量/", "cursor": first["next_cursor"]}
    )
    assert len(second.get("entries", [])) >= 10


def test_list_depth3_large_first_subdir_siblings_present(cv_env):
    cv_env.repo.write_bytes("多层/a/x.txt", b"x", commit_msg="t")
    cv_env.repo.write_bytes("多层/b/y.txt", b"y", commit_msg="t")
    for i in range(300):
        cv_env.repo.write_bytes(f"多层/big/f{i}.txt", b"z", commit_msg="t")
    cv_env.repo.write_bytes("多层/big/sub/nested.txt", b"n", commit_msg="t")
    out = cv_env.tools.list({"uri": "lore://kb/多层/", "depth": 3})
    names = {e["name"] for e in out.get("entries", [])}
    assert "a" in names
    assert "b" in names
    assert "big" in names
    assert len(out.get("entries", [])) <= 200
    assert out.get("next_cursor") is None
    assert out.get("omitted_files", 0) >= 280
    big = _dir_by_name(out["entries"], "big")
    assert big is not None and big.get("omitted_files", 0) >= 280


def test_list_depth3_omitted_files_per_dir(cv_env):
    for i in range(25):
        cv_env.repo.write_bytes(f"省略/f{i}.txt", b"x", commit_msg="t")
    out = cv_env.tools.list({"uri": "lore://kb/省略/", "depth": 2})
    files = [e for e in out.get("entries", []) if e.get("type") == "text"]
    assert len(files) == 20
    assert out.get("unlisted", 0) >= 5


def test_list_pattern_glob_recursive(cv_env):
    cv_env.repo.write_bytes("筛/a/x.TXT", b"x", commit_msg="t")
    cv_env.repo.write_bytes("筛/深/b/file.pdf", b"p", commit_msg="t")
    out = cv_env.tools.list({"uri": "lore://kb/筛/", "pattern": "*.pdf"})
    assert any(e.get("name") == "file.pdf" for e in out.get("entries", []))


def test_list_pattern_contains_and_title(cv_env):
    cv_env.repo.write_doc(
        "筛/合同.md",
        {"title": "采购合同正文", "tags": [], "source": "t"},
        "# x",
        commit_msg="t",
    )
    cv_env.repo.write_bytes("筛/其它.txt", b"x", commit_msg="t")
    out = cv_env.tools.list({"uri": "lore://kb/筛/", "pattern": "合同"})
    names = {e.get("name") for e in out.get("entries", [])}
    assert "合同.md" in names


def test_list_type_dir_and_binary(cv_env):
    cv_env.repo.write_bytes("类型/a.bin", b"\x00", commit_msg="t")
    cv_env.repo.write_bytes("类型/sub/x.txt", b"t", commit_msg="t")
    dirs = cv_env.tools.list({"uri": "lore://kb/类型/", "type": "dir"})
    assert all(e.get("type") == "dir" for e in dirs.get("entries", []))
    bins = cv_env.tools.list({"uri": "lore://kb/类型/", "type": "binary", "depth": 2})
    assert any(e.get("type") == "binary" for e in bins.get("entries", []))


def test_list_conversation_ts_filter(cv_env):
    rid = cv_env.roles.create(name="ts角色", system_prompt="")["id"]
    old = cv_env.conv.create(role_id=rid)
    new = cv_env.conv.create(role_id=rid)
    cv_env.conv.conn.execute(
        "UPDATE conversations SET updated_at = ?, last_user_message_at = ? WHERE id = ?",
        ("2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00", old),
    )
    cv_env.conv.conn.execute(
        "UPDATE conversations SET updated_at = ?, last_user_message_at = ? WHERE id = ?",
        ("2026-06-15T00:00:00+00:00", "2026-06-15T00:00:00+00:00", new),
    )
    cv_env.conv.conn.commit()
    out = cv_env.tools.list(
        {
            "uri": f"lore://conversations/dm/{rid}/",
            "ts_after": "2026-06-01",
            "ts_before": "2026-07-01",
        }
    )
    ids = {e["name"] for e in out.get("entries", [])}
    assert new in ids
    assert old not in ids


def test_list_pattern_matches_conversation_title(cv_env):
    rid = cv_env.roles.create(name="标题筛", system_prompt="")["id"]
    cid = cv_env.conv.create(role_id=rid, title="特殊合同讨论")
    out = cv_env.tools.list(
        {
            "uri": f"lore://conversations/dm/{rid}/",
            "pattern": "*合同*",
        }
    )
    assert any(e.get("name") == cid for e in out.get("entries", []))


def test_list_single_missing_matches_read_error(cv_env):
    cases = [
        "lore://kb/nope/none.md",
        "lore://kb/nope.txt",
        "lore://memory/owner/identity/fact_nope",
        "lore://conversations/dm/default/conv_does_not_exist/",
    ]
    for uri in cases:
        listed = cv_env.tools.list({"uri": uri})
        read_back = cv_env.tools.read({"uri": uri})
        assert listed.get("error") == read_back.get("error") == "not_found"
        assert not listed.get("entries")


def test_kb_dir_or_file_decided_by_disk_not_trailing_slash(cv_env):
    cv_env.repo.write_bytes("斜杠/x.txt", b"x", commit_msg="t")
    for uri in ("lore://kb/斜杠", "斜杠", "斜杠/"):
        out = cv_env.tools.list({"uri": uri})
        assert out.get("error") is None, uri
        assert out["uri"] == "lore://kb/斜杠/"
        assert [e["uri"] for e in out["entries"]] == ["lore://kb/斜杠/x.txt"]

    for uri in ("lore://kb/斜杠/x.txt", "斜杠/x.txt", "lore://kb/斜杠/x.txt/"):
        listed = cv_env.tools.list({"uri": uri})
        assert listed.get("error") is None, uri
        assert listed["uri"] == "lore://kb/斜杠/x.txt"
        assert listed["entries"][0]["type"] == "text"
        read_back = cv_env.tools.read({"uri": uri})
        assert read_back.get("error") is None, uri
        assert read_back.get("body") == "x"

    as_dir = cv_env.tools.read({"uri": "lore://kb/斜杠"})
    assert as_dir.get("error") == "is_directory"


def test_list_single_kb_file_session_memory(cv_env):
    cv_env.repo.write_doc(
        "单/项.md",
        {"title": "T", "tags": [], "source": "t"},
        "# b",
        commit_msg="t",
    )
    f = cv_env.tools.list({"uri": "lore://kb/单/项.md"})
    assert f.get("error") is None
    assert len(f.get("entries", [])) == 1
    cid = cv_env.conv.create(role_id="default")
    c = cv_env.tools.list({"uri": f"lore://conversations/dm/default/{cid}/"})
    assert c.get("error") is None
    assert len(c.get("entries", [])) == 1
    cv_env.owner.remember("单条记忆", origin="explicit_remember")
    fact = cv_env.owner.store.list_confirmed()[0]
    m = cv_env.tools.list(
        {
            "uri": f"lore://memory/owner/{fact['category']}/{fact['id']}",
        }
    )
    assert m.get("error") is None
    assert len(m.get("entries", [])) == 1


def test_list_lore_root_depth2(cv_env):
    cv_env.repo.write_bytes("根测/x.txt", b"x", commit_msg="t")
    out = cv_env.tools.list({"uri": "lore://", "depth": 2})
    uris = {e.get("uri") for e in out.get("entries", [])}
    assert "lore://kb/" in uris
    assert any(u.startswith("lore://kb/") and u != "lore://kb/" for u in uris)


def test_list_depth_string_and_invalid(cv_env):
    cv_env.repo.write_bytes("深/a.txt", b"x", commit_msg="t")
    cv_env.repo.write_bytes("深/sub/b.txt", b"y", commit_msg="t")
    out = cv_env.tools.list({"uri": "lore://kb/深/", "depth": "2"})
    assert any(e.get("name") == "sub" for e in out.get("entries", []))
    for bad in ("全部", None, True):
        ok = cv_env.tools.list({"uri": "lore://kb/深/", "depth": bad})
        assert ok.get("error") is None


def test_channel_list_deep_no_leak(cv_env):
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
    root = cv_env.tools.list({"uri": "lore://", "depth": 5}, conversation_id=cid_a)
    text = str(root)
    assert cid_b not in text
    assert "dm/" not in text
    assert "rooms/" not in text
    convs = cv_env.tools.list(
        {"uri": "lore://conversations/", "pattern": "*"},
        conversation_id=cid_a,
    )
    for e in convs.get("entries", []):
        assert e.get("name") != cid_b


def _dir_by_name(entries, name):
    return next((e for e in entries if e.get("name") == name and e.get("type") == "dir"), None)


def _write_nested_kb_probe(cv_env):
    cv_env.repo.write_bytes("A/x.txt", b"x", commit_msg="t")
    cv_env.repo.write_bytes("A/B/z.txt", b"z", commit_msg="t")
    cv_env.repo.write_bytes("A/B/C/y.txt", b"y", commit_msg="t")


def test_list_kb_root_nested_depth4(cv_env):
    _write_nested_kb_probe(cv_env)
    out = cv_env.tools.list({"uri": "lore://kb/", "depth": 4})
    uris = {e["uri"] for e in out.get("entries", [])}
    assert "lore://kb/A/" in uris
    assert "lore://kb/A/B/" in uris
    assert "lore://kb/A/B/C/" in uris
    assert "lore://kb/A/x.txt" in uris
    assert "lore://kb/A/B/z.txt" in uris
    assert "lore://kb/A/B/C/y.txt" in uris
    a = _dir_by_name(out["entries"], "A")
    b = next(e for e in out["entries"] if e.get("uri") == "lore://kb/A/B/")
    assert a.get("child_count") == 3
    assert b.get("child_count") == 2


def test_list_lore_root_kb_nested_depth3(cv_env):
    _write_nested_kb_probe(cv_env)
    out = cv_env.tools.list({"uri": "lore://", "depth": 3})
    uris = {e["uri"] for e in out.get("entries", [])}
    assert "lore://kb/A/x.txt" in uris
    assert "lore://kb/A/B/" in uris


def test_list_kb_root_pattern_star_all(cv_env):
    _write_nested_kb_probe(cv_env)
    out = cv_env.tools.list({"uri": "lore://kb/", "pattern": "*"})
    uris = {e["uri"] for e in out.get("entries", [])}
    assert len(uris) >= 6
    assert "lore://kb/A/B/C/y.txt" in uris


def test_list_dm_depth2_includes_role_and_conversation(cv_env):
    rid = cv_env.roles.create(name="探测角色", system_prompt="")["id"]
    cid = cv_env.conv.create(role_id=rid)
    cv_env.repo.write_bytes("A/x.txt", b"x", commit_msg="t")
    out = cv_env.tools.list({"uri": "lore://conversations/dm/", "depth": 2})
    assert len(out.get("entries", [])) >= 2
    role_ent = _dir_by_name(out["entries"], "探测角色") or _dir_by_name(
        out["entries"], rid
    )
    assert role_ent is not None
    assert role_ent.get("expanded") is True
    assert any(e.get("name") == cid for e in out["entries"])


def test_list_conversations_depth3_includes_dm_role_session(cv_env):
    rid = cv_env.roles.create(name="深角", system_prompt="")["id"]
    cid = cv_env.conv.create(role_id=rid)
    out = cv_env.tools.list({"uri": "lore://conversations/", "depth": 3})
    dm = _dir_by_name(out["entries"], "dm")
    assert dm is not None and dm.get("expanded") is True
    assert any(e.get("name") == cid for e in out["entries"])


def test_list_lore_root_depth3_conversations_and_memory(cv_env):
    cv_env.owner.remember("探测记忆", origin="explicit_remember")
    fact = cv_env.owner.store.list_confirmed()[0]
    kind = fact.get("category") or "preference"
    rid = cv_env.roles.create(name="根角", system_prompt="")["id"]
    cid = cv_env.conv.create(role_id=rid)
    cv_env.repo.write_bytes("A/x.txt", b"x", commit_msg="t")
    out = cv_env.tools.list({"uri": "lore://", "depth": 3})
    conv = _dir_by_name(out["entries"], "conversations")
    mem = _dir_by_name(out["entries"], "memory")
    assert conv is not None and conv.get("expanded") is True
    assert mem is not None and mem.get("expanded") is True
    assert any(
        e.get("uri", "").startswith(f"lore://memory/owner/{kind}/") for e in out["entries"]
    )
    assert any(
        e.get("uri", "").startswith(f"lore://conversations/dm/{rid}/") for e in out["entries"]
    )


def test_list_memory_owner_depth2_includes_kind(cv_env):
    cv_env.owner.remember("种类探测", origin="explicit_remember")
    fact = cv_env.owner.store.list_confirmed()[0]
    kind = fact.get("category") or "preference"
    out = cv_env.tools.list({"uri": "lore://memory/", "depth": 2})
    owner = _dir_by_name(out["entries"], "owner")
    assert owner is not None and owner.get("expanded") is True
    assert any(e.get("name") == kind for e in out["entries"])


@pytest.mark.parametrize(
    "uri",
    [
        "lore://kb/",
        "lore://kb/一致/",
        "lore://conversations/dm/",
        "lore://memory/owner/",
        "lore://",
    ],
)
def test_list_depth3_matches_star_filter(cv_env, uri):
    _write_nested_kb_probe(cv_env)
    cv_env.repo.write_bytes("一致/a.txt", b"a", commit_msg="t")
    rid = cv_env.roles.create(name="一致角", system_prompt="")["id"]
    cv_env.conv.create(role_id=rid)
    cv_env.owner.remember("一致记忆", origin="explicit_remember")
    plain = cv_env.tools.list({"uri": uri, "depth": 3})
    filt = cv_env.tools.list({"uri": uri, "depth": 3, "pattern": "*"})
    u_plain = {e["uri"] for e in plain.get("entries", [])}
    u_filt = {e["uri"] for e in filt.get("entries", [])}
    assert u_plain == u_filt
    if uri == "lore://kb/":
        assert "lore://kb/A/B/" in u_plain
    if uri == "lore://":
        assert any(u.startswith("lore://kb/A/") and u != "lore://kb/A/" for u in u_plain)


def test_list_ts_filter_only_conversations(cv_env):
    rid = cv_env.roles.create(name="ts仅会话", system_prompt="")["id"]
    cv_env.conv.create(role_id=rid)
    cv_env.repo.write_bytes("A/x.txt", b"x", commit_msg="t")
    cv_env.owner.remember("ts记忆", origin="explicit_remember")
    out = cv_env.tools.list({"uri": "lore://", "ts_after": "2000-01-01"})
    entries = out.get("entries") or []
    assert entries
    assert all(e.get("type") == "conversation" for e in entries)


def test_list_conversations_ts_excludes_old(cv_env):
    rid = cv_env.roles.create(name="ts排", system_prompt="")["id"]
    old = cv_env.conv.create(role_id=rid)
    new = cv_env.conv.create(role_id=rid)
    cv_env.conv.conn.execute(
        "UPDATE conversations SET updated_at = ?, last_user_message_at = ? WHERE id = ?",
        ("2020-01-01T00:00:00+00:00", "2020-01-01T00:00:00+00:00", old),
    )
    cv_env.conv.conn.execute(
        "UPDATE conversations SET updated_at = ?, last_user_message_at = ? WHERE id = ?",
        ("2026-06-01T00:00:00+00:00", "2026-06-01T00:00:00+00:00", new),
    )
    cv_env.conv.conn.commit()
    out = cv_env.tools.list(
        {
            "uri": "lore://conversations/",
            "ts_after": "2026-01-01",
            "ts_before": "2027-01-01",
        }
    )
    names = {e.get("name") for e in out.get("entries", [])}
    assert new in names
    assert old not in names


def test_list_lazy_title_reads_only_output_docs(cv_env, monkeypatch):
    calls = {"n": 0}
    real = __import__(
        "app.engine.context_view.listing", fromlist=["_kb_doc_title"]
    )._kb_doc_title

    def counted(path):
        calls["n"] += 1
        return real(path)

    monkeypatch.setattr(
        "app.engine.context_view.listing._kb_doc_title", counted
    )
    for i in range(300):
        cv_env.repo.write_doc(
            f"延迟/文{i}.md",
            {"title": f"T{i}", "tags": [], "source": "t"},
            "# b",
            commit_msg="t",
        )
    out = cv_env.tools.list({"uri": "lore://kb/延迟/", "depth": 5})
    doc_n = sum(1 for e in out.get("entries", []) if e.get("type") == "doc")
    assert calls["n"] <= doc_n


def test_list_budget_fair_sibling_after_large_dir(cv_env):
    for i in range(250):
        cv_env.repo.write_bytes(f"公平/大/f{i}.txt", b"x", commit_msg="t")
    cv_env.repo.write_bytes("公平/小/a.txt", b"a", commit_msg="t")
    cv_env.repo.write_bytes("公平/小/b.txt", b"b", commit_msg="t")
    out = cv_env.tools.list({"uri": "lore://kb/公平/", "depth": 2})
    names = {e["name"] for e in out.get("entries", [])}
    assert "小" in names
    big = _dir_by_name(out["entries"], "大")
    assert big is not None and big.get("expanded") is True
    assert big.get("omitted_files", 0) >= 230
