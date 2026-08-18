import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from seed.run import load_script, validate_script

SCRIPT = Path(__file__).resolve().parents[1] / "seed" / "script.yaml"


def test_script_parses():
    assert load_script(SCRIPT)["conversations"]


def test_script_has_six_conversations():
    assert len(load_script(SCRIPT)["conversations"]) == 6


def test_script_keys_are_unique():
    keys = [c["key"] for c in load_script(SCRIPT)["conversations"]]
    assert len(keys) == len(set(keys))


def test_script_passes_validation():
    assert validate_script(load_script(SCRIPT)) == []


def test_validation_catches_empty_turns():
    problems = validate_script({"conversations": [{"key": "a", "turns": []}]})
    assert problems


def test_validation_catches_duplicate_keys():
    script = {
        "conversations": [
            {"key": "a", "turns": [{"text": "x"}]},
            {"key": "a", "turns": [{"text": "y"}]},
        ]
    }
    assert validate_script(script)


def test_skill_assets_have_trigger_header():
    """无 YAML 触发头的 Skill 包在启用与对话时都会报错。"""
    root = Path(__file__).resolve().parents[1] / "assets" / "knowledge" / "技能"
    for skill_md in root.rglob("SKILL.md"):
        text = skill_md.read_text(encoding="utf-8")
        assert text.startswith("---"), skill_md
        assert "name:" in text and "description:" in text, skill_md
