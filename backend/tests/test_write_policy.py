from app.engine.write_policy import resolve_write_mode


def test_resolve_write_mode_auto_is_merge():
    assert resolve_write_mode("技能/demo/SKILL.md", "auto") == "merge"
    assert resolve_write_mode("技术/a.md", "auto") == "merge"


def test_resolve_write_mode_explicit():
    assert resolve_write_mode("技能/demo/SKILL.md", "replace") == "replace"
    assert resolve_write_mode("a.md", "merge") == "merge"
