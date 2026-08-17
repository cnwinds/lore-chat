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
