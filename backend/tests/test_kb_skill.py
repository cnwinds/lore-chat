from app.engine.kb_skill import discover_skill_roots, skill_entry_rel_path
from app.engine.skills_dir import clamp_skills_scan_dir, ensure_skills_dir
from app.storage.repo import KnowledgeRepo
import pytest


def test_discover_skill_roots_nested(tmp_path):
    repo = KnowledgeRepo(tmp_path)
    repo.write_doc(
        "技能/职业规划/张雪峰/SKILL.md",
        {"title": "张雪峰"},
        "# Skill\n",
        commit_msg="seed",
    )
    repo.write_doc(
        "技能/other/SKILL.md",
        {"title": "Other"},
        "# Other\n",
        commit_msg="seed",
    )
    # 固定目录外的包在 skills_dir 过滤下不可见
    repo.write_doc(
        "elsewhere/pkg/SKILL.md",
        {"title": "Out"},
        "# Out\n",
        commit_msg="seed",
    )
    assert discover_skill_roots(repo, "技能", skills_dir="技能") == [
        "技能/other",
        "技能/职业规划/张雪峰",
    ]
    assert discover_skill_roots(repo, "技能/职业规划", skills_dir="技能") == [
        "技能/职业规划/张雪峰"
    ]
    assert discover_skill_roots(repo, "技能/职业规划/张雪峰", skills_dir="技能") == [
        "技能/职业规划/张雪峰"
    ]
    assert discover_skill_roots(repo, "elsewhere", skills_dir="技能") == []


def test_skill_entry_rel_path():
    assert skill_entry_rel_path("a/b") == "a/b/SKILL.md"
    with pytest.raises(ValueError, match="不能为空"):
        skill_entry_rel_path("")


def test_discover_requires_skills_dir(tmp_path):
    repo = KnowledgeRepo(tmp_path / "kb")
    with pytest.raises(TypeError):
        discover_skill_roots(repo, "技能")  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="不能为空"):
        discover_skill_roots(repo, "技能", skills_dir="")


def test_discover_ignores_packages_outside_skills_dir(tmp_path):
    repo = KnowledgeRepo(tmp_path)
    repo.write_doc(
        "elsewhere/pkg/SKILL.md",
        {"title": "Out"},
        "# Out\n",
        commit_msg="seed",
    )
    assert discover_skill_roots(repo, "elsewhere", skills_dir="技能") == []


def test_clamp_skills_scan_dir():
    assert clamp_skills_scan_dir("", "技能") == "技能"
    assert clamp_skills_scan_dir("技能/foo", "技能") == "技能/foo"
    with pytest.raises(ValueError, match="技能"):
        clamp_skills_scan_dir("其它", "技能")


def test_ensure_skills_dir(tmp_path):
    repo = KnowledgeRepo(tmp_path)
    name = ensure_skills_dir(repo, "技能")
    assert name == "技能"
    assert (tmp_path / "技能" / ".gitkeep").is_file()
