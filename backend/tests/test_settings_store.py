from pathlib import Path

from app.config import Settings
from app.settings_store import EDITABLE_SETTING_KEYS, SettingsStore


def test_kb_path_not_editable():
    assert "kb_path" not in EDITABLE_SETTING_KEYS


def test_load_defaults_then_override(tmp_path: Path):
    base = Settings(kb_path=tmp_path, openai_api_key="sk-base", small_model="m1")
    store = SettingsStore(tmp_path, base)
    assert store.get().small_model == "m1"
    store.update({"small_model": "m2", "openai_api_key": "sk-new-key-xxxx"})
    assert store.get().small_model == "m2"
    assert store.get().openai_api_key == "sk-new-key-xxxx"
    assert (tmp_path / ".kb" / "settings.json").is_file()
    # 重新加载
    store2 = SettingsStore(tmp_path, base)
    assert store2.get().small_model == "m2"


def test_public_dict_masks_secrets(tmp_path: Path):
    base = Settings(kb_path=tmp_path, openai_api_key="sk-abcdefghijklmnop")
    store = SettingsStore(tmp_path, base)
    pub = store.public_dict()
    assert pub["openai_api_key"] != "sk-abcdefghijklmnop"
    assert pub["openai_api_key"].endswith("mnop")
    assert "kb_path" in pub


def test_update_rejects_kb_path(tmp_path: Path):
    base = Settings(kb_path=tmp_path)
    store = SettingsStore(tmp_path, base)
    try:
        store.update({"kb_path": "/tmp/other"})
        assert False, "expected error"
    except ValueError as e:
        assert "kb_path" in str(e).lower() or "not editable" in str(e).lower()


def test_omitted_secret_keeps_previous(tmp_path: Path):
    base = Settings(kb_path=tmp_path, openai_api_key="sk-keep-me-1234")
    store = SettingsStore(tmp_path, base)
    store.update({"openai_api_key": "sk-keep-me-1234"})
    store.update({"small_model": "x", "openai_api_key": ""})
    assert store.get().openai_api_key == "sk-keep-me-1234"


def test_null_secret_keeps_previous(tmp_path: Path):
    base = Settings(kb_path=tmp_path, openai_api_key="sk-keep-me-1234")
    store = SettingsStore(tmp_path, base)
    store.update({"openai_api_key": "sk-keep-me-1234"})
    store.update({"small_model": "y", "openai_api_key": None})
    assert store.get().openai_api_key == "sk-keep-me-1234"


def test_missing_secret_key_keeps_previous(tmp_path: Path):
    base = Settings(kb_path=tmp_path, openai_api_key="sk-keep-me-1234")
    store = SettingsStore(tmp_path, base)
    store.update({"openai_api_key": "sk-keep-me-1234"})
    store.update({"small_model": "z"})
    assert store.get().openai_api_key == "sk-keep-me-1234"
