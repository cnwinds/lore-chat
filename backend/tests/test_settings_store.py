import json
from pathlib import Path

from app.config import Settings
from app.settings_store import EDITABLE_SETTING_KEYS, SettingsStore


def test_kb_path_not_editable():
    assert "kb_path" not in EDITABLE_SETTING_KEYS


def test_new_kb_does_not_seed_default_models(tmp_path: Path):
    store = SettingsStore(tmp_path, Settings(kb_path=tmp_path))
    s = store.get()
    assert s.chat_models == []
    assert s.utility_models == []
    assert s.embed_models == []
    assert s.big_model == ""
    assert s.small_model == ""
    assert s.embed_model == ""
    path = tmp_path / ".kb" / "settings.json"
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        assert not data.get("chat_models")
        assert not data.get("utility_models")
        assert not data.get("embed_models")


def test_store_explicit_empty_chains_not_resurrected_from_env(tmp_path: Path):
    kb = tmp_path / ".kb"
    kb.mkdir()
    (kb / "settings.json").write_text(
        json.dumps(
            {
                "chat_models": [],
                "utility_models": [],
                "embed_models": [],
            }
        ),
        encoding="utf-8",
    )
    base = Settings(
        kb_path=tmp_path,
        big_model="gpt-4o",
        small_model="gpt-4o-mini",
        embed_model="text-embedding-3-small",
        openai_base_url="https://api.openai.com/v1",
    )
    store = SettingsStore(tmp_path, base)
    s = store.get()
    assert s.chat_models == []
    assert s.utility_models == []
    assert s.embed_models == []
    assert s.big_model == ""
    assert s.small_model == ""
    assert s.embed_model == ""


def test_store_env_legacy_names_migrate_when_chain_key_absent(tmp_path: Path):
    store = SettingsStore(
        tmp_path,
        Settings(kb_path=tmp_path, big_model="gpt-4o", small_model="gpt-4o-mini"),
    )
    s = store.get()
    assert s.chat_models[0]["model"] == "gpt-4o"
    assert s.utility_models[0]["model"] == "gpt-4o-mini"


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
    # 全局 openai_api_key 不计入已配置；须写在 chat/utility 候选上
    assert pub["llm_api_key_configured"] is False
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


def test_public_dict_configured_via_candidate_key(tmp_path: Path):
    base = Settings(
        kb_path=tmp_path,
        openai_api_key="sk-none",
        chat_models=[
            {
                "id": "c1",
                "model": "gpt-4o",
                "base_url": "https://example.com/v1",
                "api_key": "sk-cand-abcd",
            }
        ],
        utility_models=[
            {
                "id": "u1",
                "model": "gpt-4o-mini",
                "base_url": "https://example.com/v1",
                "api_key": "sk-util-abcd",
            }
        ],
    )
    store = SettingsStore(tmp_path, base)
    pub = store.public_dict()
    assert pub["llm_api_key_configured"] is True


def test_migrate_promotes_global_openai_into_candidates():
    from app.models.candidate import migrate_settings_dict, sync_legacy_aliases

    out = sync_legacy_aliases(
        migrate_settings_dict(
            {
                "openai_api_key": "sk-real-key-1234",
                "openai_base_url": "https://api.openai.com/v1",
                "chat_models": [{"id": "c1", "model": "gpt-4o"}],
                "utility_models": [{"id": "u1", "model": "gpt-4o-mini"}],
                "embed_model": "text-embedding-3-small",
            }
        )
    )
    assert out["chat_models"][0]["api_key"] == "sk-real-key-1234"
    assert out["chat_models"][0]["base_url"] == "https://api.openai.com/v1"
    assert out["utility_models"][0]["api_key"] == "sk-real-key-1234"
    assert out["embed_models"][0]["api_key"] == "sk-real-key-1234"
    assert out["embed_models"][0]["base_url"] == "https://api.openai.com/v1"
    assert out["embed_api_key"] == "sk-real-key-1234"
    assert out["embed_base_url"] == "https://api.openai.com/v1"


def test_store_promotes_then_configured(tmp_path: Path):
    """仅有全局 openai_* 时，启动迁移写入候选后视为已配置。"""
    base = Settings(
        kb_path=tmp_path,
        openai_api_key="sk-abcdefghijklmnop",
        openai_base_url="https://api.openai.com/v1",
        chat_models=[{"id": "c1", "model": "gpt-4o"}],
        utility_models=[{"id": "u1", "model": "gpt-4o-mini"}],
    )
    store = SettingsStore(tmp_path, base)
    s = store.get()
    assert s.chat_models[0]["api_key"] == "sk-abcdefghijklmnop"
    assert store.public_dict()["llm_api_key_configured"] is True
