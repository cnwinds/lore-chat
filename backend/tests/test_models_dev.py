"""models.dev 索引 / 搜索 / 与 catalog 合并。"""

from __future__ import annotations

from app.models.catalog import (
    lookup_capabilities,
    merge_catalog_hits,
    search_supplement,
    set_active_models_dev_store,
)
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
                "reasoning_options": [
                    {"type": "effort", "values": ["low", "medium", "high"]}
                ],
            },
        }
    },
    "deepseek": {
        "models": {
            "deepseek-v4-pro": {
                "name": "DeepSeek V4 Pro",
                "modalities": {"input": ["text"], "output": ["text"]},
                "reasoning": True,
                "reasoning_options": [
                    {"type": "effort", "values": ["low", "medium", "high"]}
                ],
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
    assert hit.effort_options == ()


def test_parse_uses_reasoning_options_not_heuristics():
    hit = parse_remote_model(
        "openai",
        "gpt-5.2",
        {
            "modalities": {"input": ["text", "image"]},
            "reasoning": True,
            "reasoning_options": [
                {"type": "effort", "values": ["none", "high", "xhigh"]},
                {"type": "toggle"},
            ],
        },
    )
    assert hit.thinking is True
    # 不按 gpt-5.2 启发补全为 five 档， strictly 用 JSON
    assert hit.effort_options == ("none", "high", "xhigh")


def test_parse_empty_reasoning_options_no_invented_efforts():
    hit = parse_remote_model(
        "zenmux",
        "sapiens-ai/agnes-1.5-pro",
        {
            "modalities": {"input": ["text"]},
            "reasoning": True,
            "reasoning_options": [],
        },
    )
    assert hit.thinking is True
    assert hit.effort_options == ()


def test_filter_catalog_hits_shared():
    from app.models.models_dev import filter_catalog_hits, unique_hits_by_id

    idx = index_payload(
        {
            "p": {
                "models": {
                    "agnes-2.5-pro": {
                        "name": "Agnes",
                        "reasoning": True,
                        "reasoning_options": [],
                        "modalities": {"input": ["text"]},
                    }
                }
            }
        }
    )
    # provider/id 双键不应让 unique 丢条目
    assert any(h.id == "agnes-2.5-pro" for h in unique_hits_by_id(idx))
    hits = filter_catalog_hits(unique_hits_by_id(idx), "agnes", kind="llm")
    assert [h.id for h in hits] == ["agnes-2.5-pro"]


def test_index_and_search(tmp_path):
    store = ModelsDevStore(tmp_path / "cache.json", ttl_sec=3600)
    store._index = index_payload(SAMPLE)
    store._fetched_at = 1e12
    store._source = "cache"
    hits = store.search("gpt")
    assert any(h.id == "gpt-4o" for h in hits)
    assert store.lookup("o3") is not None
    assert store.lookup("o3").thinking is True
    assert store.lookup("o3").effort_options == ("low", "medium", "high")


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
    caps = _from_hit(hit, source="models_dev")
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


def test_lookup_models_dev_over_supplement(tmp_path):
    store = ModelsDevStore(tmp_path / "cache.json")
    store._index = index_payload(SAMPLE)
    set_active_models_dev_store(store)
    try:
        # models.dev 命中优先（即使补充文件也有 gpt-4o）
        g = lookup_capabilities("gpt-4o", models_dev=store)
        assert g.source == "models_dev"
        assert g.thinking is False
        assert g.effort_options == ()

        # 补充：Agnes 2.5 不在 SAMPLE
        a = lookup_capabilities("agnes-2.5-pro", models_dev=store)
        assert a.source == "supplement"
        assert a.image_wire == "url"
        assert a.thinking is True
        assert a.effort_options == ()
        assert a.thinking_protocol == "agnes"

        # 仅目录有的 id
        store._index.update(
            index_payload(
                {
                    "x": {
                        "models": {
                            "brand-new-vision": {
                                "modalities": {"input": ["text", "image"]},
                                "reasoning": True,
                                "reasoning_options": [
                                    {"type": "effort", "values": ["minimal", "high"]}
                                ],
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
        assert n.effort_options == ("minimal", "high")
    finally:
        set_active_models_dev_store(None)


def test_supplement_search_agnes():
    hits = search_supplement("agnes-2.5", kind="llm")
    assert any(h.id == "agnes-2.5-pro" for h in hits)
    assert all(h.thinking_protocol == "agnes" for h in hits if h.id.startswith("agnes-2.5"))


def test_merge_catalog_hits_prefers_primary():
    from app.models.models_dev import CatalogHit

    def _hit(mid: str, *, thinking: bool = False) -> CatalogHit:
        return CatalogHit(
            provider="p",
            id=mid,
            name=mid,
            image=False,
            thinking=thinking,
            effort="medium",
            effort_options=("medium",) if thinking else (),
            image_wire="data",
            thinking_protocol="none",
        )

    primary = [_hit("a"), _hit("b")]
    extra = [_hit("b", thinking=True), _hit("c")]
    merged = merge_catalog_hits(primary, extra, limit=10)
    assert [h.id for h in merged] == ["a", "b", "c"]
    assert merged[1].thinking is False


def test_merge_prefer_extra_puts_supplement_first():
    from app.models.models_dev import CatalogHit

    def _hit(mid: str) -> CatalogHit:
        return CatalogHit(
            provider="p",
            id=mid,
            name=mid,
            image=False,
            thinking=False,
            effort="medium",
            effort_options=(),
            image_wire="data",
            thinking_protocol="none",
        )

    primary = [_hit(f"remote-{i}") for i in range(10)]
    extra = [_hit("agnes-2.5-pro"), _hit("agnes-2.5-flash")]
    merged = merge_catalog_hits(primary, extra, limit=5, prefer_extra=True)
    assert merged[0].id == "agnes-2.5-pro"
    assert merged[1].id == "agnes-2.5-flash"
    assert len(merged) == 5


def test_search_slash_model_ids():
    payload = {
        "zenmux": {
            "models": {
                "sapiens-ai/agnes-1.5-pro": {
                    "name": "Agnes 1.5 Pro",
                    "reasoning": True,
                    "reasoning_options": [],
                    "modalities": {"input": ["text"], "output": ["text"]},
                }
            }
        }
    }
    store = ModelsDevStore("/tmp/unused-cache.json")
    store._index = index_payload(payload)
    store._fetched_at = 1e12
    hits = store.search("agnes", kind="llm")
    assert any(h.id == "sapiens-ai/agnes-1.5-pro" for h in hits)
