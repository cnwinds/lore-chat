"""models.dev 索引 / 搜索 / 与 catalog 合并。"""

from __future__ import annotations

from app.models.catalog import lookup_capabilities, set_active_models_dev_store
from app.models.models_dev import ModelsDevStore, index_payload, parse_remote_model


SAMPLE = {
    "openai": {
        "models": {
            "gpt-4o": {
                "name": "GPT-4o",
                "modalities": {"input": ["text", "image"], "output": ["text"]},
                "reasoning": False,
            },
            "o3": {
                "name": "o3",
                "modalities": {"input": ["text", "image"], "output": ["text"]},
                "reasoning": True,
            },
        }
    },
    "deepseek": {
        "models": {
            "deepseek-v4-pro": {
                "name": "DeepSeek V4 Pro",
                "modalities": {"input": ["text"], "output": ["text"]},
                "reasoning": True,
            }
        }
    },
}


def test_parse_remote_model_image_and_thinking():
    hit = parse_remote_model(
        "openai",
        "gpt-4o",
        {"modalities": {"input": ["text", "image"]}, "reasoning": False, "name": "GPT-4o"},
    )
    assert hit.image is True
    assert hit.thinking is False
    assert hit.image_wire == "data"


def test_index_and_search(tmp_path):
    store = ModelsDevStore(tmp_path / "cache.json", ttl_sec=3600)
    store._index = index_payload(SAMPLE)
    store._fetched_at = 1e12
    store._source = "cache"
    hits = store.search("gpt")
    assert any(h.id == "gpt-4o" for h in hits)
    assert store.lookup("o3") is not None
    assert store.lookup("o3").thinking is True


def test_from_hit_keeps_catalog_effort(tmp_path):
    from app.models.catalog import _from_hit
    from app.models.models_dev import CatalogHit

    hit = CatalogHit(
        provider="openai",
        id="text-embedding-3-small",
        name="text-embedding-3-small",
        image=False,
        thinking=False,
        effort="medium",
        effort_options=("medium",),
        image_wire="data",
        thinking_protocol="none",
        embedding=True,
    )
    caps = _from_hit(hit)
    assert caps.effort_options == ("medium",)
    assert caps.source == "models_dev"


def test_search_kind_embedding(tmp_path):
    payload = {
        **SAMPLE,
        "openai": {
            "models": {
                **SAMPLE["openai"]["models"],
                "text-embedding-3-small": {
                    "name": "text-embedding-3-small",
                    "family": "text-embedding",
                    "modalities": {"input": ["text"], "output": ["text"]},
                },
            }
        },
    }
    store = ModelsDevStore(tmp_path / "cache.json", ttl_sec=3600)
    store._index = index_payload(payload)
    store._fetched_at = 1e12
    emb = store.search("", kind="embedding", limit=50)
    assert all(h.embedding for h in emb)
    assert any(h.id == "text-embedding-3-small" for h in emb)
    llm = store.search("gpt", kind="llm")
    assert all(not h.embedding for h in llm)
    assert any(h.id == "gpt-4o" for h in llm)


def test_lookup_prefers_preset_then_models_dev(tmp_path):
    store = ModelsDevStore(tmp_path / "cache.json")
    store._index = index_payload(SAMPLE)
    set_active_models_dev_store(store)
    try:
        # preset 覆盖 Agnes
        a = lookup_capabilities("agnes-2.5-pro", models_dev=store)
        assert a.image_wire == "url"
        assert a.source == "preset"
        # models.dev 命中
        g = lookup_capabilities("gpt-4o", models_dev=store)
        # gpt-4o 也在 preset
        assert g.source == "preset"
        # 仅目录有的 id
        store._index.update(
            index_payload(
                {
                    "x": {
                        "models": {
                            "brand-new-vision": {
                                "modalities": {"input": ["text", "image"]},
                                "reasoning": True,
                            }
                        }
                    }
                }
            )
        )
        n = lookup_capabilities("brand-new-vision", models_dev=store)
        assert n.source == "models_dev"
        assert n.image is True
        assert n.thinking is True
        assert n.effort == "medium"
    finally:
        set_active_models_dev_store(None)
