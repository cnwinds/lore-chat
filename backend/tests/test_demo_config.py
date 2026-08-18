from app.config import EDITABLE_SETTING_KEYS, Settings


def test_demo_mode_defaults_to_false():
    assert Settings(kb_path="./knowledge").demo_mode is False


def test_demo_mode_reads_env(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    assert Settings(kb_path="./knowledge").demo_mode is True


def test_demo_mode_is_not_hot_editable():
    """部署级开关：可从设置页热改就等于只读能被 UI 关掉。"""
    assert "demo_mode" not in EDITABLE_SETTING_KEYS
