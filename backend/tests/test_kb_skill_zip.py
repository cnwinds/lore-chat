import io
import zipfile

import pytest

from app.engine.kb_skill_zip import (
    is_zip_filename,
    parse_skill_zip_entries,
    skill_zip_package_name,
)
from app.engine.knowledge_writer import KbPathExistsError, KnowledgeWriter
from app.index.fulltext import FullTextIndex
from app.index.indexer import Indexer
from app.index.vector import VectorIndex
from app.models.llm import FakeLLMClient
from app.storage.repo import KnowledgeRepo


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _writer(tmp_path):
    repo = KnowledgeRepo(tmp_path / "knowledge")
    llm = FakeLLMClient(embed_dim=8)
    idx = Indexer(VectorIndex(tmp_path / "vec"), FullTextIndex(tmp_path / "fts.db"), llm)
    return KnowledgeWriter(repo, idx), repo


def test_is_zip_filename_and_package_name():
    assert is_zip_filename("数数查询.zip")
    assert is_zip_filename("Foo.ZIP")
    assert not is_zip_filename("SKILL.md")
    assert skill_zip_package_name("数数查询.zip") == "数数查询"
    assert skill_zip_package_name("数数查询 (1).ZIP") == "数数查询 (1)"
    with pytest.raises(ValueError, match="无效"):
        skill_zip_package_name(".zip")


def test_parse_strips_download_wrapper_and_junk():
    data = _zip_bytes(
        {
            "数数查询/SKILL.md": b"---\nname: n\ndescription: d\n---\n\n# n\n",
            "数数查询/scripts/run.py": b"print(1)\n",
            "数数查询/.DS_Store": b"junk",
            "__MACOSX/数数查询/._SKILL.md": b"apple",
        }
    )
    entries = dict(parse_skill_zip_entries(data))
    assert set(entries) == {"SKILL.md", "scripts/run.py"}
    assert entries["SKILL.md"].startswith(b"---\n")


def test_parse_skill_md_at_zip_root():
    data = _zip_bytes({"SKILL.md": b"# skill\n", "notes.md": b"# n\n"})
    entries = dict(parse_skill_zip_entries(data))
    assert set(entries) == {"SKILL.md", "notes.md"}


def test_parse_normalizes_skill_md_case():
    data = _zip_bytes({"pkg/skill.md": b"# skill\n"})
    entries = dict(parse_skill_zip_entries(data))
    assert "SKILL.md" in entries
    assert "skill.md" not in entries


def test_parse_rejects_missing_skill_md():
    data = _zip_bytes({"pkg/readme.md": b"# hi\n"})
    with pytest.raises(ValueError, match="SKILL.md"):
        parse_skill_zip_entries(data)


def test_parse_rejects_zip_slip():
    from app.engine.kb_skill_zip import _normalize_member

    with pytest.raises(ValueError, match="不合法"):
        _normalize_member("../outside/SKILL.md")
    with pytest.raises(ValueError, match="不合法"):
        _normalize_member("ok/foo/../../etc/SKILL.md")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(zipfile.ZipInfo("../outside/SKILL.md"), b"# x\n")
    with pytest.raises(ValueError, match="不合法|没有可导入"):
        parse_skill_zip_entries(buf.getvalue())


def test_parse_rejects_empty_and_garbage():
    with pytest.raises(ValueError, match="空"):
        parse_skill_zip_entries(b"")
    with pytest.raises(ValueError, match="不是有效"):
        parse_skill_zip_entries(b"not-a-zip")


def test_import_skill_zip_under_skills_dir(tmp_path):
    writer, repo = _writer(tmp_path)
    data = _zip_bytes(
        {
            "数数查询/SKILL.md": b"---\nname: count\ndescription: 数数\n---\n\n# 数\n",
            "数数查询/scripts/run.py": b"print(1)\n",
        }
    )
    result = writer.import_entry(
        directory="技能", filename="数数查询.zip", data=data
    )
    assert result["kind"] == "skill_package"
    assert result["rel_path"] == "技能/数数查询"
    assert "技能/数数查询/SKILL.md" in repo.list_tree()
    assert "技能/数数查询/scripts/run.py" in repo.list_tree()
    assert "技能/数数查询.zip" not in repo.list_tree()
    body = repo.read_doc("技能/数数查询/SKILL.md").body
    assert "name: count" in body


def test_import_skill_zip_into_skills_subdir(tmp_path):
    writer, repo = _writer(tmp_path)
    data = _zip_bytes({"pkg/SKILL.md": b"# skill\n"})
    result = writer.import_entry(
        directory="技能/职业规划", filename="张雪峰.zip", data=data
    )
    assert result["rel_path"] == "技能/职业规划/张雪峰"
    assert "技能/职业规划/张雪峰/SKILL.md" in repo.list_tree()


def test_import_skill_zip_conflict(tmp_path):
    writer, repo = _writer(tmp_path)
    writer.import_entry(
        directory="技能/数数查询",
        filename="SKILL.md",
        data=b"# existing\n",
    )
    data = _zip_bytes({"数数查询/SKILL.md": b"# new\n"})
    with pytest.raises(KbPathExistsError) as ei:
        writer.import_entry(directory="技能", filename="数数查询.zip", data=data)
    assert ei.value.rel_path == "技能/数数查询"
    assert repo.read_doc("技能/数数查询/SKILL.md").body.startswith("# existing")


def test_import_zip_outside_skills_stays_file(tmp_path):
    writer, repo = _writer(tmp_path)
    data = _zip_bytes({"数数查询/SKILL.md": b"# skill\n"})
    result = writer.import_entry(
        directory="技术", filename="数数查询.zip", data=data
    )
    assert result["kind"] == "file"
    assert result["rel_path"] == "技术/数数查询.zip"
    assert repo.abs_path("技术/数数查询.zip").is_file()
    assert "技能/数数查询/SKILL.md" not in repo.list_tree()


def test_import_non_skill_zip_into_skills_rejected(tmp_path):
    writer, _repo = _writer(tmp_path)
    data = _zip_bytes({"readme.md": b"# hi\n"})
    with pytest.raises(ValueError, match="SKILL.md"):
        writer.import_entry(directory="技能", filename="docs.zip", data=data)
