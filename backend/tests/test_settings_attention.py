"""settings attention 红点聚合。"""

from __future__ import annotations

from app.config import Settings
from app.settings_attention import (
    build_settings_attention,
    chain_needs_setup,
    count_incomplete_prices,
    price_row_needs_setup,
)


def test_chain_needs_setup_requires_model_url_key(tmp_path):
    empty = Settings(kb_path=tmp_path, openai_api_key="sk-none", chat_models=[])
    assert chain_needs_setup(empty, "chat") is True

    partial = Settings(
        kb_path=tmp_path,
        chat_models=[
            {
                "id": "c1",
                "model": "gpt-4o",
                "base_url": "https://api.openai.com/v1",
                "api_key": None,
            }
        ],
    )
    assert chain_needs_setup(partial, "chat") is True

    ok = Settings(
        kb_path=tmp_path,
        chat_models=[
            {
                "id": "c1",
                "model": "gpt-4o",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-real-key",
            }
        ],
        utility_models=[
            {
                "id": "u1",
                "model": "mini",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-real-key",
            }
        ],
        embed_models=[
            {
                "id": "e1",
                "model": "text-embedding-3-small",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-real-key",
            }
        ],
    )
    assert chain_needs_setup(ok, "chat") is False
    assert chain_needs_setup(ok, "utility") is False
    assert chain_needs_setup(ok, "embed") is False


def test_price_row_needs_setup():
    assert price_row_needs_setup(
        {
            "model": "gpt-4o",
            "kinds": ["chat"],
            "prompt_per_1m": None,
            "completion_per_1m": 1.0,
            "embed_per_1m": None,
        }
    )
    assert not price_row_needs_setup(
        {
            "model": "gpt-4o",
            "kinds": ["chat"],
            "prompt_per_1m": 1.0,
            "completion_per_1m": 2.0,
            "embed_per_1m": None,
        }
    )
    assert price_row_needs_setup(
        {
            "model": "text-embedding-3-small",
            "kinds": ["embed"],
            "prompt_per_1m": None,
            "completion_per_1m": None,
            "embed_per_1m": None,
        }
    )
    assert count_incomplete_prices(
        [
            {
                "model": "a",
                "kinds": ["chat"],
                "prompt_per_1m": None,
                "completion_per_1m": None,
            },
            {
                "model": "b",
                "kinds": ["chat"],
                "prompt_per_1m": 1,
                "completion_per_1m": 2,
            },
        ]
    ) == 1


def test_build_settings_attention_flags(tmp_path):
    settings = Settings(
        kb_path=tmp_path,
        chat_models=[
            {
                "id": "c1",
                "model": "gpt-4o",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-real",
            }
        ],
        utility_models=[],
        embed_models=[],
    )
    att = build_settings_attention(
        settings=settings,
        memory_pending_count=2,
        incomplete_price_count=1,
    )
    assert att["model"]["chat"] is False
    assert att["model"]["utility"] is True
    assert att["model"]["embed"] is True
    assert att["model"]["any"] is True
    assert att["memory"]["any"] is True
    assert att["memory"]["pending_count"] == 2
    assert att["usage"]["any"] is True
    assert att["any"] is True
