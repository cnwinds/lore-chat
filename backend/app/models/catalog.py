"""模型能力目录：models.dev 优先 → 本地补充 JSON → 前缀启发 → 默认。

不再用 Python 硬编码覆盖在线目录；强度档位来自 JSON 的 reasoning_options。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.models.candidate import ImageWire, ThinkingProtocol
from app.models.effort import Effort, coerce_to_options, pick_default_effort, supported_efforts
from app.models.models_dev import (
    CatalogHit,
    ModelsDevStore,
    filter_catalog_hits,
    index_payload,
    infer_image_wire,
    infer_thinking_protocol,
    unique_hits_by_id,
)

_log = logging.getLogger("lorechat.catalog")

_SUPPLEMENT_PATH = Path(__file__).with_name("catalog_supplement.json")


@dataclass(frozen=True)
class ModelCapabilities:
    image: bool = False
    thinking: bool = False
    image_wire: ImageWire = "data"
    thinking_protocol: ThinkingProtocol = "none"
    effort: Effort = "medium"
    effort_options: tuple[Effort, ...] = ()
    source: str = "default"  # models_dev|supplement|prefix|default


def _with_efforts(
    *,
    model: str,
    image: bool,
    thinking: bool,
    image_wire: ImageWire,
    thinking_protocol: ThinkingProtocol,
    source: str,
    effort_options: tuple[Effort, ...] | None = None,
) -> ModelCapabilities:
    if effort_options is None:
        opts = supported_efforts(model, thinking_protocol) if thinking else ()
    else:
        opts = effort_options
    return ModelCapabilities(
        image=image,
        thinking=thinking,
        image_wire=image_wire,
        thinking_protocol=thinking_protocol,
        effort=pick_default_effort(opts, model=model),
        effort_options=opts,
        source=source,
    )


@lru_cache(maxsize=1)
def _supplement_index() -> dict[str, CatalogHit]:
    if not _SUPPLEMENT_PATH.is_file():
        _log.warning("catalog supplement missing: %s", _SUPPLEMENT_PATH)
        return {}
    try:
        raw = json.loads(_SUPPLEMENT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        _log.warning("catalog supplement read failed: %s", e)
        return {}
    if not isinstance(raw, dict):
        return {}
    # 去掉文档字段，保持与 models.dev provider 根一致
    payload = {k: v for k, v in raw.items() if not str(k).startswith("_") and isinstance(v, dict)}
    return index_payload(payload)


def reload_supplement_for_tests() -> None:
    """测试用：清掉补充索引缓存。"""
    _supplement_index.cache_clear()


def _normalize_model_id(model: str) -> str:
    return (model or "").strip().lower()


def _from_hit(hit: CatalogHit, *, source: str) -> ModelCapabilities:
    opts = hit.effort_options
    effort = hit.effort if (not opts or hit.effort in opts) else pick_default_effort(opts, model=hit.id)
    return ModelCapabilities(
        image=hit.image,
        thinking=hit.thinking,
        image_wire=hit.image_wire,
        thinking_protocol=hit.thinking_protocol,
        effort=effort,
        effort_options=opts,
        source=source,
    )


def _lookup_supplement(model: str) -> CatalogHit | None:
    mid = _normalize_model_id(model)
    if not mid:
        return None
    return _supplement_index().get(mid)


def _prefix_caps(model: str, base_url: str | None) -> ModelCapabilities | None:
    mid = _normalize_model_id(model)
    protocol = infer_thinking_protocol(mid, base_url)
    wire = infer_image_wire(mid, protocol)
    if mid.startswith("agnes-") or "agnes-ai.com" in (base_url or "").lower():
        return _with_efforts(
            model=mid,
            image=True,
            thinking=True,
            image_wire=wire,
            thinking_protocol=protocol,
            source="prefix",
        )
    if mid.startswith("deepseek-"):
        return _with_efforts(
            model=mid,
            image=False,
            thinking=True,
            image_wire=wire,
            thinking_protocol=protocol,
            source="prefix",
        )
    if mid.startswith("qwen"):
        return _with_efforts(
            model=mid,
            image=True,
            thinking=True,
            image_wire=wire,
            thinking_protocol=protocol,
            source="prefix",
        )
    if mid.startswith(("o1", "o3", "o4")) or mid.startswith("gpt-5"):
        return _with_efforts(
            model=mid,
            image=True,
            thinking=True,
            image_wire=wire,
            thinking_protocol="openai_kwargs",
            source="prefix",
        )
    return None


def lookup_capabilities(
    model: str,
    base_url: str | None = None,
    *,
    models_dev: ModelsDevStore | None = None,
) -> ModelCapabilities:
    """能力解析：在线目录 > 本地补充 > 前缀启发 > 默认。"""
    mid = _normalize_model_id(model)

    if models_dev is not None:
        hit = models_dev.lookup(mid)
        if hit is not None:
            return _from_hit(hit, source="models_dev")

    supp = _lookup_supplement(mid)
    if supp is not None:
        return _from_hit(supp, source="supplement")

    # gpt-5.2-* 变体：补充文件仅精确 id；前缀仍覆盖家族
    if mid.startswith("gpt-5.2"):
        return _with_efforts(
            model=mid,
            image=True,
            thinking=True,
            image_wire="data",
            thinking_protocol="openai_kwargs",
            source="prefix",
        )

    prefixed = _prefix_caps(model, base_url)
    if prefixed is not None:
        return prefixed
    return ModelCapabilities()


def search_supplement(
    query: str,
    *,
    limit: int = 40,
    kind: str | None = None,
) -> list[CatalogHit]:
    """搜索本地补充（供目录 API 与 models.dev 结果合并）。"""
    return filter_catalog_hits(
        unique_hits_by_id(_supplement_index()),
        query,
        limit=limit,
        kind=kind,
    )


def merge_catalog_hits(
    primary: list[CatalogHit],
    extra: list[CatalogHit],
    *,
    limit: int,
    prefer_extra: bool = False,
) -> list[CatalogHit]:
    """primary（通常 models.dev）同 id 优先；extra 补洞。

    prefer_extra=True（有搜索词时）：先列补充命中，避免被远程长列表挤掉。
    """
    limit = max(1, min(int(limit), 100))
    by_id: dict[str, CatalogHit] = {}
    primary_order: list[str] = []
    extra_order: list[str] = []

    for h in primary:
        key = h.id.lower()
        if key in by_id:
            continue
        by_id[key] = h
        primary_order.append(key)

    for h in extra:
        key = h.id.lower()
        if key in by_id:
            continue
        by_id[key] = h
        extra_order.append(key)

    if prefer_extra:
        # 过滤场景：保证补充模型可见，并为它们预留名额
        reserve = min(len(extra_order), limit)
        room = limit - reserve
        keys = extra_order[:reserve] + primary_order[:room]
    else:
        keys = primary_order + extra_order
        keys = keys[:limit]
    return [by_id[k] for k in keys]


# 进程级可选注入（admin / enrich 共用）
_ACTIVE_STORE: ModelsDevStore | None = None


def set_active_models_dev_store(store: ModelsDevStore | None) -> None:
    global _ACTIVE_STORE
    _ACTIVE_STORE = store


def get_active_models_dev_store() -> ModelsDevStore | None:
    return _ACTIVE_STORE


def enrich_candidate_dict(item: dict[str, Any]) -> dict[str, Any]:
    """能力预填；thinking_protocol / 缺省能力随目录自适应。"""
    out = dict(item)
    model = str(out.get("model") or "")
    base_url = out.get("base_url")
    caps = lookup_capabilities(
        model,
        base_url if isinstance(base_url, str) else None,
        models_dev=_ACTIVE_STORE,
    )
    if "image" not in out:
        out["image"] = caps.image
    if "thinking" not in out:
        out["thinking"] = caps.thinking
    if "image_wire" not in out:
        out["image_wire"] = caps.image_wire
    out["thinking_protocol"] = caps.thinking_protocol
    out["effort_options"] = list(caps.effort_options)
    if "effort" not in out:
        out["effort"] = caps.effort if caps.thinking else "medium"
    else:
        out["effort"] = coerce_to_options(
            str(out.get("effort")),
            caps.effort_options,
            model=model,
        )
    return out
