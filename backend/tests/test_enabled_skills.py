from app.engine.enabled_skills import (
    EnabledSkillsError,
    EnabledSkillsStore,
    build_skill_catalog,
)
from app.engine.kb_skill import skill_trigger_fields
from app.storage.repo import KnowledgeRepo
import pytest


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
