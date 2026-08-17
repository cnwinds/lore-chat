"""provider /models 列表解析与能力 enrich。"""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx

from app.config import Settings
from app.models.catalog import catalog_hit_for_model_id
from app.models.provider_models import (
    list_provider_models,
    parse_models_list_payload,
)
from app.settings_store import resolve_api_key_from_settings


def test_parse_models_list_payload_openai_shape():
    ids = parse_models_list_payload(
        {"data": [{"id": "gpt-4o"}, {"id": "deepseek-v4-pro"}, {"id": "gpt-4o"}]}
    )
    assert ids == ["gpt-4o", "deepseek-v4-pro"]


def test_parse_models_list_payload_alt_shapes():
    assert parse_models_list_payload([{"model": "a"}, "b"]) == ["a", "b"]
    assert parse_models_list_payload({"models": [{"id": "x"}]}) == ["x"]


def test_catalog_hit_uses_supplement_json():
    hit = catalog_hit_for_model_id("deepseek-v4-pro", models_dev=None)
    assert hit.thinking is True
    assert hit.image is False
    assert hit.thinking_protocol == "deepseek"
    assert list(hit.effort_options) == ["low", "medium", "high", "max"]


def test_resolve_api_key_prefers_body_then_candidate():
    settings = MagicMock()
    settings.chat_models = [
        {"id": "c1", "api_key": "sk-saved-xxxx"},
    ]
    settings.utility_models = []
    settings.image_providers = [
        {"id": "openai", "api_key": "sk-image-yyyy"},
    ]
    settings.embed_api_key = None
    assert (
        resolve_api_key_from_settings(
            settings, api_key="sk-typed-yyyy", candidate_id="c1"
        )
        == "sk-typed-yyyy"
    )
    assert (
        resolve_api_key_from_settings(settings, api_key="sk***yyyy", candidate_id="c1")
        == "sk-saved-xxxx"
    )
    assert (
        resolve_api_key_from_settings(settings, api_key="", candidate_id="c1")
        == "sk-saved-xxxx"
    )
    assert (
        resolve_api_key_from_settings(
            settings, api_key="", candidate_id="openai"
        )
        == "sk-image-yyyy"
    )


def test_list_provider_models_from_remote(monkeypatch):
    def fake_fetch(*, base_url, api_key, timeout_sec=8.0):
        assert base_url.endswith("/v1") or "example.com" in base_url
        return [
            "deepseek-v4-pro",
            "unknown-chat-xyz",
            "text-embedding-v3",
            "bge-m3",
            "dall-e-3",
            "cogview-4",
        ]

    monkeypatch.setattr(
        "app.models.provider_models.fetch_remote_model_ids", fake_fetch
    )
    llm = list_provider_models(
        base_url="https://example.com/v1",
        api_key="sk-test",
        kind="llm",
        models_dev=None,
    )
    assert llm["source"] == "provider"
    llm_ids = [i["id"] for i in llm["items"]]
    assert "deepseek-v4-pro" in llm_ids
    assert "unknown-chat-xyz" in llm_ids
    assert "text-embedding-v3" not in llm_ids
    assert "bge-m3" not in llm_ids
    assert "dall-e-3" not in llm_ids

    emb = list_provider_models(
        base_url="https://example.com/v1",
        api_key="sk-test",
        kind="embedding",
        models_dev=None,
    )
    emb_ids = [i["id"] for i in emb["items"]]
    assert emb_ids == ["text-embedding-v3", "bge-m3"]
    ds = next(i for i in llm["items"] if i["id"] == "deepseek-v4-pro")
    assert ds["thinking"] is True
    assert ds["effort_options"] == ["low", "medium", "high", "max"]

    img = list_provider_models(
        base_url="https://example.com/v1",
        api_key="sk-test",
        kind="image",
        models_dev=None,
    )
    img_ids = [i["id"] for i in img["items"]]
    assert img_ids == ["dall-e-3", "cogview-4"]


def test_is_embedding_heuristic_covers_bailian_style():
    from app.models.models_dev import is_embedding_model, is_image_gen_model

    assert is_embedding_model("text-embedding-v3")
    assert is_embedding_model("multimodal-embedding-v1")
    assert is_embedding_model("bge-large-zh-v1.5")
    assert not is_embedding_model("qwen-plus")
    assert not is_embedding_model("deepseek-v4-pro")

    assert is_image_gen_model("dall-e-3")
    assert is_image_gen_model("wan2.6-t2i")
    assert is_image_gen_model("agnes-image-2.1-flash")
    assert not is_image_gen_model("gpt-4o")
    assert not is_image_gen_model("text-embedding-v3")


def test_list_provider_models_image_fallback_when_remote_empty(monkeypatch):
    from app.models.catalog import reload_supplement_for_tests

    reload_supplement_for_tests()

    def fake_fetch(*, base_url, api_key, timeout_sec=8.0):
        return ["gpt-4o", "qwen-plus"]

    monkeypatch.setattr(
        "app.models.provider_models.fetch_remote_model_ids", fake_fetch
    )
    out = list_provider_models(
        base_url="https://example.com/v1",
        api_key="sk-test",
        kind="image",
        models_dev=None,
    )
    assert out["source"] == "catalog_fallback"
    ids = [i["id"] for i in out["items"]]
    assert "dall-e-3" in ids
    assert "cogview-4" in ids
    assert "gpt-4o" not in ids


def test_list_provider_models_fallback_on_error(monkeypatch):
    def boom(*, base_url, api_key, timeout_sec=8.0):
        raise httpx.ConnectError("nope")

    monkeypatch.setattr("app.models.provider_models.fetch_remote_model_ids", boom)
    out = list_provider_models(
        base_url="https://example.com/v1",
        api_key="sk-test",
        q="deepseek",
        kind="llm",
        models_dev=None,
    )
    assert out["source"] == "catalog_fallback"
    assert out["error"]
    assert any(i["id"].startswith("deepseek") for i in out["items"])


def test_settings_have_llm_ignores_global_openai_only(tmp_path):
    from app.settings_store import SettingsStore, settings_have_llm_api_key

    base = Settings(
        kb_path=tmp_path,
        openai_api_key="sk-global-only",
        chat_models=[
            {"id": "c1", "model": "gpt-4o", "base_url": None, "api_key": None}
        ],
        utility_models=[
            {"id": "u1", "model": "mini", "base_url": None, "api_key": None}
        ],
    )
    # 构造未提升的 settings（绕过 store 迁移）：直接断言函数
    s = base
    # 若链上无 key，即使有全局 openai 也不算已配置
    assert settings_have_llm_api_key(s) is False
