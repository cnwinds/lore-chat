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
    assert pub["llm_api_key_configured"] is True
    assert "kb_path" in pub


def test_public_dict_placeholder_not_configured(tmp_path: Path):
    base = Settings(kb_path=tmp_path, openai_api_key="sk-none")
    store = SettingsStore(tmp_path, base)
    pub = store.public_dict()
    assert pub["llm_api_key_configured"] is False
    assert pub["openai_api_key"] is None


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


def test_search_providers_empty_clears_legacy(tmp_path: Path):
    base = Settings(kb_path=tmp_path, tavily_api_key="tv-secret-xxxx")
    store = SettingsStore(tmp_path, base)
    # 启动迁移后应有链
    assert any(p.get("provider") == "tavily" for p in store.get().search_providers)
    store.update({"search_providers": []})
    assert store.get().search_providers == []
    assert store.get().tavily_api_key is None
    # 再次加载不应从 legacy 复活
    store2 = SettingsStore(tmp_path, Settings(kb_path=tmp_path))
    assert store2.get().search_providers == []


def test_search_providers_mask_and_keep_key(tmp_path: Path):
    base = Settings(kb_path=tmp_path)
    store = SettingsStore(tmp_path, base)
    store.update(
        {
            "search_providers": [
                {"id": "tavily", "provider": "tavily", "api_key": "tv-abcdefghijklmnop"},
            ]
        }
    )
    pub = store.public_dict()
    assert pub["search_providers"][0]["api_key"] != "tv-abcdefghijklmnop"
    assert "***" in pub["search_providers"][0]["api_key"]
    store.update(
        {
            "search_providers": [
                {"id": "tavily", "provider": "tavily", "api_key": "tv***mnop"},
            ]
        }
    )
    assert store.get().search_providers[0]["api_key"] == "tv-abcdefghijklmnop"


def test_search_providers_reject_duplicate(tmp_path: Path):
    from app.engine.web.search_providers import DuplicateSearchProviderError

    base = Settings(kb_path=tmp_path)
    store = SettingsStore(tmp_path, base)
    try:
        store.update(
            {
                "search_providers": [
                    {"id": "tavily", "provider": "tavily", "api_key": "a"},
                    {"id": "t2", "provider": "tavily", "api_key": "b"},
                ]
            }
        )
        assert False, "expected DuplicateSearchProviderError"
    except DuplicateSearchProviderError:
        pass
