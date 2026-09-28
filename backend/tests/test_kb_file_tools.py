"""write_kb_file / read 文本资产 / stage_to_sandbox。"""

from __future__ import annotations

import pytest

from app.engine.agent.prompts import MODE_DEFAULT, MODE_NO_WRITE
from app.engine.agent.tool_catalog import resolve_tool_label, select_tools
from app.engine.knowledge_writer import KbPathExistsError
from app.storage.kb_text_files import is_kb_text_file
from app.storage.repo import KnowledgeRepo
from tests.helpers import make_writer
from tests.test_sandbox_tools import _make_registry, _tool_names


def test_is_kb_text_file_allowlist():
    assert is_kb_text_file("scripts/run.sh")
    assert is_kb_text_file("fetch.py")
    assert is_kb_text_file("Dockerfile")
    assert not is_kb_text_file("note.md")
    assert not is_kb_text_file("shot.png")


def test_resolve_tool_label_svg_vs_code():
    assert (
        resolve_tool_label("write_kb_file", {"filename": "logo.svg"})
        == "写入知识库矢量图"
    )
    assert (
        resolve_tool_label("write_kb_file", {"filename": "run.sh"})
        == "写入知识库代码/文本文件"
    )
    assert resolve_tool_label("generate_image", {}) == "生成图片"


def test_write_text_file_and_overwrite(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    w = make_writer(repo, tmp_path)
    r = w.write_text_file(
        directory="scripts",
        filename="run.sh",
        content="#!/bin/sh\necho a\n",
    )
    assert r["rel_path"] == "scripts/run.sh"
    assert r["overwritten"] is False
    assert repo.abs_path("scripts/run.sh").read_text(encoding="utf-8").startswith(
        "#!/bin/sh"
    )

    with pytest.raises(KbPathExistsError):
        w.write_text_file(
            directory="scripts",
            filename="run.sh",
            content="#!/bin/sh\necho b\n",
        )

    r2 = w.write_text_file(
        directory="scripts",
        filename="run.sh",
        content="#!/bin/sh\necho b\n",
        overwrite=True,
    )
    assert r2["overwritten"] is True
    assert "echo b" in repo.abs_path("scripts/run.sh").read_text(encoding="utf-8")


def test_write_text_file_rejects_md(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    w = make_writer(repo, tmp_path)
    with pytest.raises(ValueError, match="write_doc"):
        w.write_text_file(directory="x", filename="a.md", content="# hi\n")


def test_write_text_file_allows_svg(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    w = make_writer(repo, tmp_path)
    svg = '<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>\n'
    r = w.write_text_file(
        directory="备忘",
        filename="logo.svg",
        content=svg,
    )
    # SVG 忽略备忘等目录，固定落媒体/生成/{年月}；入库时补 XML 声明便于 <img>
    assert r["rel_path"].startswith("媒体/生成/")
    assert r["rel_path"].endswith("/logo.svg")
    written = repo.abs_path(r["rel_path"]).read_text(encoding="utf-8")
    assert written.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert '<svg xmlns="http://www.w3.org/2000/svg">' in written


@pytest.mark.asyncio
async def test_write_kb_file_svg_returns_attachments(tmp_path):
    registry, _ = _make_registry(tmp_path)
    svg = '<svg xmlns="http://www.w3.org/2000/svg"><circle r="5"/></svg>\n'
    out = await registry.execute(
        "write_kb_file",
        {
            "directory": "备忘",
            "filename": "mark.svg",
            "content": svg,
        },
    )
    assert out.get("status") == "saved"
    rel = out.get("rel_path") or ""
    assert rel.startswith("媒体/生成/") and rel.endswith("/mark.svg")
    assert out.get("attachments") == [rel]
    written = registry.repo.abs_path(rel).read_text(encoding="utf-8")
    assert written.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "<circle r=\"5\"/>" in written


def test_write_text_file_rejects_unknown_binary_ext(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    w = make_writer(repo, tmp_path)
    with pytest.raises(ValueError, match="不支持的文件类型"):
        w.write_text_file(directory="x", filename="a.bin", content="x")


def test_write_text_file_rejects_raster_image(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    w = make_writer(repo, tmp_path)
    with pytest.raises(ValueError, match="generate_image|publish_from_sandbox"):
        w.write_text_file(directory="图", filename="a.png", content="not-a-png")


@pytest.mark.asyncio
async def test_write_kb_file_tool_roundtrip(tmp_path):
    registry, _ = _make_registry(tmp_path)
    created = await registry.execute(
        "write_kb_file",
        {
            "directory": "scripts",
            "filename": "hello.py",
            "content": "print('hi')\n",
        },
    )
    assert created.get("status") == "saved"
    assert created.get("rel_path") == "scripts/hello.py"

    conflict = await registry.execute(
        "write_kb_file",
        {
            "directory": "scripts",
            "filename": "hello.py",
            "content": "print('bye')\n",
        },
    )
    assert conflict.get("error") == "ALREADY_EXISTS"

    overwritten = await registry.execute(
        "write_kb_file",
        {
            "directory": "scripts",
            "filename": "hello.py",
            "content": "print('bye')\n",
            "overwrite": True,
        },
    )
    assert overwritten.get("overwritten") is True

    read = await registry.execute("read_doc", {"path": "scripts/hello.py"})
    assert "print('bye')" in (read.get("body") or "")
    assert read.get("kind") == "file"
    assert "outline" not in read


@pytest.mark.asyncio
async def test_write_kb_file_rejects_binary_ext(tmp_path):
    registry, _ = _make_registry(tmp_path)
    r = await registry.execute(
        "write_kb_file",
        {
            "directory": "bin",
            "filename": "a.png",
            "content": "not-png",
        },
    )
    assert r.get("status") == "failed"
    assert r.get("error") == "INVALID"


@pytest.mark.asyncio
async def test_stage_to_sandbox_default_path(tmp_path):
    registry, runtime = _make_registry(tmp_path)
    assert runtime is not None
    await registry.execute(
        "write_kb_file",
        {
            "directory": "scripts",
            "filename": "echo.sh",
            "content": "#!/bin/sh\necho staged\n",
        },
    )
    staged = await registry.execute(
        "stage_to_sandbox", {"kb_path": "scripts/echo.sh"}
    )
    assert staged.get("sandbox_path") == "/workspace/scripts/echo.sh"
    data = await runtime.read_file("/workspace/scripts/echo.sh")
    assert b"echo staged" in data

    # 覆盖
    await registry.execute(
        "write_kb_file",
        {
            "directory": "scripts",
            "filename": "echo.sh",
            "content": "#!/bin/sh\necho v2\n",
            "overwrite": True,
        },
    )
    staged2 = await registry.execute(
        "stage_to_sandbox",
        {
            "kb_path": "scripts/echo.sh",
            "sandbox_path": "/workspace/custom.sh",
        },
    )
    assert staged2.get("sandbox_path") == "/workspace/custom.sh"
    assert b"echo v2" in await runtime.read_file("/workspace/custom.sh")


@pytest.mark.asyncio
async def test_stage_to_sandbox_batch(tmp_path):
    registry, runtime = _make_registry(tmp_path)
    assert runtime is not None
    for name, body in (
        ("a.sh", "#!/bin/sh\necho a\n"),
        ("b.py", "print('b')\n"),
    ):
        await registry.execute(
            "write_kb_file",
            {"directory": "scripts", "filename": name, "content": body},
        )
    staged = await registry.execute(
        "stage_to_sandbox",
        {
            "files": [
                {"kb_path": "scripts/a.sh"},
                {
                    "kb_path": "scripts/b.py",
                    "sandbox_path": "/workspace/run/b.py",
                },
            ]
        },
    )
    assert staged.get("ok") == 2
    assert staged.get("failed") == 0
    assert len(staged["items"]) == 2
    assert b"echo a" in await runtime.read_file("/workspace/scripts/a.sh")
    assert b"print('b')" in await runtime.read_file("/workspace/run/b.py")


def test_select_tools_no_write_drops_write_kb_file_keeps_stage():
    names = _tool_names(
        select_tools(MODE_NO_WRITE, web_enabled=True, sandbox_enabled=True)
    )
    assert "write_kb_file" not in names
    assert "stage_to_sandbox" in names
    assert "write_doc" not in names


def test_select_tools_includes_write_kb_file_by_default():
    names = _tool_names(select_tools(MODE_DEFAULT, web_enabled=True))
    assert "write_kb_file" in names
    assert "stage_to_sandbox" not in names  # sandbox off


@pytest.mark.asyncio
async def test_edit_doc_rejects_non_markdown(tmp_path):
    registry, _ = _make_registry(tmp_path)
    await registry.execute(
        "write_kb_file",
        {
            "directory": "scripts",
            "filename": "x.py",
            "content": "print(1)\n",
        },
    )
    r = await registry.execute(
        "edit_doc",
        {
            "path": "scripts/x.py",
            "edits": [{"old_string": "print(1)", "new_string": "print(2)"}],
        },
        conversation_id="c1",
    )
    assert r.get("error") == "NOT_MARKDOWN"


@pytest.mark.asyncio
async def test_stage_rejects_path_escape(tmp_path):
    registry, _ = _make_registry(tmp_path)
    await registry.execute(
        "write_kb_file",
        {
            "directory": "scripts",
            "filename": "x.sh",
            "content": "#!/bin/sh\n",
        },
    )
    r = await registry.execute(
        "stage_to_sandbox",
        {
            "kb_path": "scripts/x.sh",
            "sandbox_path": "/workspace/../etc/passwd",
        },
    )
    assert r.get("error") == "path not under /workspace"


def _seed_kb(tmp_path, files: dict[str, str | bytes]) -> None:
    root = tmp_path / "knowledge"
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body if isinstance(body, bytes) else body.encode())


async def _missing(runtime, path: str) -> bool:
    try:
        await runtime.read_file(path)
    except FileNotFoundError:
        return True
    return False


@pytest.mark.asyncio
async def test_stage_directory_recursive_skips_hidden_and_bytecode(tmp_path):
    registry, runtime = _make_registry(tmp_path)
    _seed_kb(
        tmp_path,
        {
            "技能/demo/SKILL.md": "# demo\n",
            "技能/demo/scripts/run.py": "print(1)\n",
            "技能/demo/scripts/__pycache__/run.cpython-312.pyc": b"\x00",
            "技能/demo/stray.pyc": b"\x00",
            "技能/demo/.cache/x.txt": "hidden\n",
        },
    )
    staged = await registry.execute("stage_to_sandbox", {"kb_path": "技能/demo/"})
    assert staged.get("error") is None
    assert staged["ok"] == 2
    assert staged["sandbox_path"] == "/workspace/技能/demo"
    assert staged["items"][0]["kind"] == "dir"
    assert staged["items"][0]["files"] == 2
    # 目录内逐个文件不刷来源卡片
    assert staged["sources"] == []
    assert b"# demo" in await runtime.read_file("/workspace/技能/demo/SKILL.md")
    assert b"print(1)" in await runtime.read_file(
        "/workspace/技能/demo/scripts/run.py"
    )
    for skipped in (
        "/workspace/技能/demo/scripts/__pycache__/run.cpython-312.pyc",
        "/workspace/技能/demo/stray.pyc",
        "/workspace/技能/demo/.cache/x.txt",
    ):
        assert await _missing(runtime, skipped)


@pytest.mark.asyncio
async def test_stage_directory_to_custom_dest_mixed_with_file(tmp_path):
    registry, runtime = _make_registry(tmp_path)
    _seed_kb(
        tmp_path,
        {
            "技能/demo/a/b.txt": "b\n",
            "scripts/one.sh": "echo one\n",
        },
    )
    staged = await registry.execute(
        "stage_to_sandbox",
        {
            "files": [
                {"kb_path": "技能/demo", "sandbox_path": "/workspace/pkg"},
                {"kb_path": "scripts/one.sh"},
            ]
        },
    )
    assert staged["ok"] == 2
    assert len(staged["items"]) == 2
    assert b"b" in await runtime.read_file("/workspace/pkg/a/b.txt")
    assert b"echo one" in await runtime.read_file("/workspace/scripts/one.sh")
    # 单文件仍进来源；目录项不进
    assert staged["sources"] == [{"type": "kb", "path": "scripts/one.sh"}]


@pytest.mark.asyncio
async def test_stage_directory_clean_removes_stale_files(tmp_path):
    registry, runtime = _make_registry(tmp_path)
    _seed_kb(tmp_path, {"技能/demo/keep.py": "v2\n"})
    await runtime.write_file("/workspace/技能/demo/keep.py", b"v1\n")
    await runtime.write_file("/workspace/技能/demo/removed.py", b"stale\n")
    await runtime.write_file("/workspace/技能/other.py", b"sibling\n")

    kept = await registry.execute("stage_to_sandbox", {"kb_path": "技能/demo"})
    assert kept.get("error") is None
    assert b"stale" in await runtime.read_file("/workspace/技能/demo/removed.py")

    cleaned = await registry.execute(
        "stage_to_sandbox", {"kb_path": "技能/demo", "clean": True}
    )
    assert cleaned.get("error") is None
    assert cleaned["items"][0]["cleaned"] is True
    assert "已先清空目标" in cleaned["summary"]
    assert await _missing(runtime, "/workspace/技能/demo/removed.py")
    assert b"v2" in await runtime.read_file("/workspace/技能/demo/keep.py")
    # clean 只作用于目标目录本身
    assert b"sibling" in await runtime.read_file("/workspace/技能/other.py")


@pytest.mark.asyncio
async def test_stage_clean_rejects_file_and_workspace_roots(tmp_path):
    registry, runtime = _make_registry(tmp_path)
    _seed_kb(tmp_path, {"技能/demo/a.py": "a\n", "scripts/one.sh": "echo\n"})
    await runtime.write_file("/workspace/conversations/c1/keep.txt", b"keep\n")

    on_file = await registry.execute(
        "stage_to_sandbox", {"kb_path": "scripts/one.sh", "clean": True}
    )
    assert on_file.get("error") == "invalid clean target"

    for dest in (
        "/workspace/conversations",
        "/workspace/conversations/c1",
        "/workspace/schedules/s1",
    ):
        r = await registry.execute(
            "stage_to_sandbox",
            {"kb_path": "技能/demo", "sandbox_path": dest, "clean": True},
        )
        assert r.get("error") == "invalid clean target", dest
    assert b"keep" in await runtime.read_file("/workspace/conversations/c1/keep.txt")

    # 更深一层（任务自己的子目录）允许清空
    ok = await registry.execute(
        "stage_to_sandbox",
        {
            "kb_path": "技能/demo",
            "sandbox_path": "/workspace/conversations/c1/pkg",
            "clean": True,
        },
    )
    assert ok.get("error") is None
    assert b"keep" in await runtime.read_file("/workspace/conversations/c1/keep.txt")


@pytest.mark.asyncio
async def test_stage_rejects_internal_hidden_and_empty_dirs(tmp_path):
    registry, runtime = _make_registry(tmp_path)
    _seed_kb(
        tmp_path,
        {
            ".kb/settings.json": "{}",
            "技能/.hidden/a.txt": "x\n",
            "技能/empty/.keep": "",
        },
    )
    for kb_path in (".kb", ".kb/settings.json", ".git", "技能/.hidden", "/"):
        r = await registry.execute("stage_to_sandbox", {"kb_path": kb_path})
        assert r.get("error") in ("forbidden", "missing kb_path"), kb_path
    empty = await registry.execute("stage_to_sandbox", {"kb_path": "技能/empty"})
    assert empty.get("error") == "empty directory"
    assert await _missing(runtime, "/workspace/.kb/settings.json")


@pytest.mark.asyncio
async def test_stage_directory_limits_write_nothing(tmp_path, monkeypatch):
    from app.engine.sandbox import kb_exchange

    registry, runtime = _make_registry(tmp_path)
    _seed_kb(tmp_path, {f"技能/big/f{i}.txt": "x\n" for i in range(4)})
    monkeypatch.setattr(kb_exchange, "STAGE_MAX_FILES", 3)
    r = await registry.execute("stage_to_sandbox", {"kb_path": "技能/big"})
    assert r.get("error") == "too many files"
    assert await _missing(runtime, "/workspace/技能/big/f0.txt")

    monkeypatch.setattr(kb_exchange, "STAGE_MAX_FILES", 500)
    monkeypatch.setattr(kb_exchange, "STAGE_MAX_BYTES", 5)
    r = await registry.execute("stage_to_sandbox", {"kb_path": "技能/big"})
    assert r.get("error") == "too large"
    assert await _missing(runtime, "/workspace/技能/big/f0.txt")


@pytest.mark.asyncio
async def test_list_kb_structure_includes_scripts(tmp_path):
    registry, _ = _make_registry(tmp_path)
    await registry.execute(
        "write_kb_file",
        {
            "directory": "scripts",
            "filename": "run.sh",
            "content": "#!/bin/sh\necho ok\n",
        },
    )
    listed = await registry.execute("list_kb_structure", {})
    assert "run.sh" in listed["summary"] or any(
        "run.sh" in f
        for d in listed.get("directories", [])
        for f in d.get("files", [])
    )
