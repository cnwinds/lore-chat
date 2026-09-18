import pytest

from app.engine.enabled_skills import (
    EnabledSkillsError,
    EnabledSkillsStore,
    build_skill_catalog,
)
from app.engine.kb_skill import skill_trigger_fields
from app.storage.repo import KnowledgeRepo


def test_skill_trigger_fields_from_body_yaml_not_meta():
    body = "---\nname: from-body\ndescription: trigger me\n---\n\n# Hi\n"
    name, desc = skill_trigger_fields(body)
    assert name == "from-body"
    assert desc == "trigger me"


def test_skill_trigger_fields_multiline_description():
    body = (
        "---\nname: x\ndescription: |\n  line1\n  line2\n---\n\n# X\n"
    )
    name, desc = skill_trigger_fields(body)
    assert name == "x"
    assert desc is not None
    assert "line1" in desc and "line2" in desc


def test_build_skill_catalog_rejects_missing_header(tmp_path):
    repo = KnowledgeRepo(tmp_path)
    repo.write_doc(
        "技能/bare/SKILL.md",
        {"title": "B", "name": "meta-name"},
        "# no yaml\n",
        commit_msg="seed",
    )
    with pytest.raises(EnabledSkillsError, match="description"):
        build_skill_catalog(repo, ["技能/bare"], skills_dir="技能")


def test_enabled_skills_store_put_rewrites(tmp_path):
    repo = KnowledgeRepo(tmp_path)
    for name in ("a", "b"):
        repo.write_doc(
            f"技能/{name}/SKILL.md",
            {"title": name},
            f"---\nname: {name}\ndescription: Use {name}.\n---\n\n# {name}\n",
            commit_msg="seed",
        )
    store = EnabledSkillsStore(tmp_path, skills_dir="技能")
    store.save_roots(["技能/a", "技能/b"])
    roots = store.put(repo, ["技能/a"])
    assert roots == ["技能/a"]
    assert store.load_roots() == ["技能/a"]


def test_try_enable_root_appends_valid_and_skips_invalid(tmp_path):
    repo = KnowledgeRepo(tmp_path)
    repo.write_doc(
        "技能/a/SKILL.md",
        {"title": "a"},
        "---\nname: a\ndescription: Use a.\n---\n\n# a\n",
        commit_msg="seed",
    )
    repo.write_doc(
        "技能/bare/SKILL.md",
        {"title": "b"},
        "# no yaml\n",
        commit_msg="seed",
    )
    store = EnabledSkillsStore(tmp_path, skills_dir="技能")
    store.save_roots(["技能/a"])
    assert store.try_enable_root(repo, "技能/a") is False
    assert store.load_roots() == ["技能/a"]
    assert store.try_enable_root(repo, "技能/bare") is False
    assert store.load_roots() == ["技能/a"]

    repo.write_doc(
        "技能/c/SKILL.md",
        {"title": "c"},
        "---\nname: c\ndescription: Use c.\n---\n\n# c\n",
        commit_msg="seed",
    )
    assert store.try_enable_root(repo, "技能/c") is True
    assert store.load_roots() == ["技能/a", "技能/c"]


def test_build_skill_catalog_put_rejects_missing_package(tmp_path):
    repo = KnowledgeRepo(tmp_path)
    with pytest.raises(EnabledSkillsError, match="SKILL.md"):
        build_skill_catalog(repo, ["技能/数数查询"], skills_dir="技能")


def test_build_skill_catalog_chat_skips_missing_package(tmp_path):
    repo = KnowledgeRepo(tmp_path)
    repo.write_doc(
        "技能/ok/SKILL.md",
        {"title": "ok"},
        "---\nname: ok\ndescription: Use ok.\n---\n\n# ok\n",
        commit_msg="seed",
    )
    catalog = build_skill_catalog(
        repo,
        ["技能/数数查询", "技能/ok"],
        skills_dir="技能",
        drop_missing=True,
    )
    assert [item["root"] for item in catalog] == ["技能/ok"]


def test_prune_missing_packages_drops_deleted_keeps_present(tmp_path):
    repo = KnowledgeRepo(tmp_path)
    repo.write_doc(
        "技能/ok/SKILL.md",
        {"title": "ok"},
        "---\nname: ok\ndescription: Use ok.\n---\n\n# ok\n",
        commit_msg="seed",
    )
    store = EnabledSkillsStore(tmp_path, skills_dir="技能")
    store.save_roots(["技能/ok", "技能/数数查询"])
    assert store.prune_missing_packages(repo) == ["技能/ok"]
    assert store.load_roots() == ["技能/ok"]


def test_prune_missing_packages_noop_when_all_present(tmp_path):
    repo = KnowledgeRepo(tmp_path)
    repo.write_doc(
        "技能/ok/SKILL.md",
        {"title": "ok"},
        "---\nname: ok\ndescription: Use ok.\n---\n\n# ok\n",
        commit_msg="seed",
    )
    store = EnabledSkillsStore(tmp_path, skills_dir="技能")
    store.save_roots(["技能/ok"])
    before = (tmp_path / ".kb" / "enabled_skills.json").read_text(encoding="utf-8")
    assert store.prune_missing_packages(repo) == ["技能/ok"]
    assert (tmp_path / ".kb" / "enabled_skills.json").read_text(encoding="utf-8") == before


def test_remap_roots_rewrites_package_and_nested(tmp_path):
    store = EnabledSkillsStore(tmp_path, skills_dir="技能")
    store.save_roots(["技能/old", "技能/other"])
    assert store.remap_roots("技能/old", "技能/new") == ["技能/new", "技能/other"]
    assert store.load_roots() == ["技能/new", "技能/other"]
    # 不得把 技能/old-extra 当成 技能/old 的子路径
    store.save_roots(["技能/old-extra", "技能/old"])
    assert store.remap_roots("技能/old", "技能/new") == ["技能/old-extra", "技能/new"]
