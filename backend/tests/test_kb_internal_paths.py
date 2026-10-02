"""知识库内部路径（.kb / .git）对模型工具不可读；路径先规范化再判定。"""

from __future__ import annotations

import pytest

from app.storage.repo import KnowledgeRepo
from tests.test_sandbox_tools import _make_registry


def test_is_internal_normalizes_before_matching(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    for path in (
        ".kb",
        ".kb/settings.json",
        "/.kb/settings.json",
        "a/../.kb/settings.json",
        "./.kb/x.md",
        ".git",
        ".git/config",
        "a\\..\\.git\\config",
    ):
        assert repo.is_internal(path), path
        assert not repo.is_writable(path), path
    for path in ("", "技能/demo/SKILL.md", ".gitignore", ".github/x.yml", ".kbx/a.md"):
        assert not repo.is_internal(path), path


@pytest.mark.asyncio
async def test_read_tools_refuse_internal_paths(tmp_path):
    registry, _ = _make_registry(tmp_path)
    kb = tmp_path / "knowledge"
    (kb / ".kb").mkdir(parents=True, exist_ok=True)
    (kb / ".kb" / "settings.json").write_text('{"api_key": "sk-secret"}', encoding="utf-8")
    (kb / ".kb" / "note.md").write_text("# internal\nsk-secret\n", encoding="utf-8")

    for path in (".kb/settings.json", ".kb/note.md", "a/../.kb/settings.json", ".git/config"):
        r = await registry.execute("read", {"uri": path})
        assert r.get("error") in ("forbidden", "invalid_uri"), path
        assert "sk-secret" not in str(r)

    meta = await registry.execute("read", {"uri": ".kb/note.md"})
    assert meta.get("error") in ("forbidden", "invalid_uri", "FORBIDDEN")
    assert "sk-secret" not in str(meta)
