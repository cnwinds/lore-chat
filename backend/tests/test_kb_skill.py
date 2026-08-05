from app.engine.kb_skill import discover_skill_roots, skill_entry_rel_path
from app.storage.repo import KnowledgeRepo


def test_discover_skill_roots_nested(tmp_path):
    repo = KnowledgeRepo(tmp_path)
    repo.write_doc(
        "skill/职业规划/张雪峰/SKILL.md",
        {"title": "张雪峰"},
        "# Skill\n",
        commit_msg="seed",
    )
    repo.write_doc(
        "skill/other/SKILL.md",
        {"title": "Other"},
        "# Other\n",
        commit_msg="seed",
    )
    assert discover_skill_roots(repo, "skill") == [
        "skill/other",
        "skill/职业规划/张雪峰",
    ]
    assert discover_skill_roots(repo, "skill/职业规划") == ["skill/职业规划/张雪峰"]
    assert discover_skill_roots(repo, "skill/职业规划/张雪峰") == [
        "skill/职业规划/张雪峰"
    ]


def test_skill_entry_rel_path():
    assert skill_entry_rel_path("a/b") == "a/b/SKILL.md"
    assert skill_entry_rel_path("") == "SKILL.md"
