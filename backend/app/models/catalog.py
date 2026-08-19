"""模型能力目录：models.dev 优先 → 本地补充 JSON → 前缀启发 → 默认。

不再用 Python 硬编码覆盖在线目录；强度档位来自 JSON 的 reasoning_options。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from app.models.candidate import ImageWire, ThinkingProtocol
from app.models.effort import Effort, coerce_to_options, pick_default_effort, supported_efforts
from app.models.model_id import model_id_has_prefix, normalize_model_id
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
    return normalize_model_id(model)


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
    if model_id_has_prefix(mid, "agnes-") or "agnes-ai.com" in (base_url or "").lower():
        return _with_efforts(
            model=mid,
            image=True,
            thinking=True,
            image_wire=wire,
            thinking_protocol=protocol,
            source="prefix",
        )
    if model_id_has_prefix(mid, "deepseek-"):
        return _with_efforts(
            model=mid,
            image=False,
            thinking=True,
            image_wire=wire,
            thinking_protocol=protocol,
            source="prefix",
        )
    if model_id_has_prefix(mid, "qwen"):
        return _with_efforts(
            model=mid,
            image=True,
            thinking=True,
            image_wire=wire,
            thinking_protocol=protocol,
            source="prefix",
        )
    if model_id_has_prefix(mid, "glm"):
        return _with_efforts(
            model=mid,
            image=False,
            thinking=True,
            image_wire=wire,
            thinking_protocol=protocol,
            source="prefix",
        )
    if model_id_has_prefix(mid, "o1", "o3", "o4", "gpt-5"):
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


def capabilities_public_dict(caps: ModelCapabilities, *, model: str) -> dict[str, Any]:
    """HTTP / UI 共用的能力字段（与 catalog item 能力段同形）。"""
    mid = (model or "").strip()
    return {
        "ok": True,
        "model": mid,
        "image": caps.image,
        "thinking": caps.thinking,
        "effort": caps.effort,
        "effort_options": list(caps.effort_options),
        "image_wire": caps.image_wire,
        "thinking_protocol": caps.thinking_protocol,
        "source": caps.source,
    }


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


CatalogKind = Literal["all", "llm", "embedding", "image"]


def normalize_catalog_kind(
    kind: str | None,
    *,
    default: CatalogKind = "all",
) -> CatalogKind:
    """统一 kind 别名；未知或空串回落 default（目录搜索默认 all，provider-models 默认 llm）。"""
    k = (kind or "").strip().lower()
    if k in {"embedding", "embed"}:
        return "embedding"
    if k in {"image", "imagegen"}:
        return "image"
    if k == "llm":
        return "llm"
    if k == "all":
        return "all"
    return default


def search_known_catalog(
    query: str = "",
    *,
    limit: int = 40,
    kind: str | None = "all",
    models_dev: ModelsDevStore | None = None,
) -> list[CatalogHit]:
    """合并 models.dev + 本地补充的唯一搜索入口（admin / provider fallback 共用）。"""
    store = models_dev if models_dev is not None else get_active_models_dev_store()
    kind_n = normalize_catalog_kind(kind)
    limit_n = max(1, min(int(limit), 200))
    remote = (
        store.search(query, limit=limit_n, kind=kind_n) if store is not None else []
    )
    local = search_supplement(query, limit=limit_n, kind=kind_n)
    return merge_catalog_hits(
        remote, local, limit=limit_n, prefer_extra=bool((query or "").strip())
    )


def catalog_hit_for_model_id(
    model_id: str,
    *,
    base_url: str | None = None,
    models_dev: ModelsDevStore | None = None,
) -> CatalogHit:
    """把模型 id 解析为目录项：models.dev > 补充 JSON > 能力启发。"""
    from app.models.models_dev import is_embedding_model

    mid = (model_id or "").strip()
    store = models_dev if models_dev is not None else get_active_models_dev_store()
    if store is not None:
        hit = store.lookup(mid)
        if hit is not None:
            return hit
    for h in search_supplement(mid, limit=20, kind="all"):
        if h.id.lower() == mid.lower():
            return h
    caps = lookup_capabilities(mid, base_url, models_dev=store)
    embedding = is_embedding_model(mid)
    return CatalogHit(
        provider="remote",
        id=mid,
        name=mid,
        image=False if embedding else caps.image,
        thinking=False if embedding else caps.thinking,
        effort=caps.effort if not embedding else "medium",
        effort_options=() if embedding else caps.effort_options,
        image_wire=caps.image_wire,
        thinking_protocol="none" if embedding else caps.thinking_protocol,
        embedding=embedding,
    )


# 进程级可选注入（admin / enrich 共用）
_ACTIVE_STORE: ModelsDevStore | None = None


def set_active_models_dev_store(store: ModelsDevStore | None) -> None:
    global _ACTIVE_STORE
    _ACTIVE_STORE = store


def get_active_models_dev_store() -> ModelsDevStore | None:
    return _ACTIVE_STORE


def enrich_candidate_dict(item: dict[str, Any]) -> dict[str, Any]:
    """能力预填；thinking_protocol / 缺省能力随目录自适应。

    已保存的非空 effort_options 优先保留（选模型时可能来自某厂家更完整的档位）；
    目录未列档但候选开启思考时，用协议启发补档，避免强度下拉被掏空。
    """
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

    saved_opts = out.get("effort_options")
    saved_list = (
        [str(x).strip() for x in saved_opts if str(x).strip()]
        if isinstance(saved_opts, (list, tuple))
        else []
    )
    catalog_opts = list(caps.effort_options)
    thinking_on = bool(out.get("thinking"))
    if saved_list:
        out["effort_options"] = saved_list
    elif catalog_opts:
        out["effort_options"] = catalog_opts
    elif thinking_on:
        # Agnes 等协议本来就无档位；其余用启发补全
        proto = caps.thinking_protocol
        if proto == "agnes" or model_id_has_prefix(model, "agnes-"):
            out["effort_options"] = []
        else:
            out["effort_options"] = list(
                supported_efforts(model, proto if proto != "none" else None)
            )
    else:
        out["effort_options"] = []

    opts = tuple(out["effort_options"])
    if "effort" not in out:
        out["effort"] = (
            pick_default_effort(opts, model=model)
            if opts
            else (caps.effort if caps.thinking else "medium")
        )
    elif opts:
        out["effort"] = coerce_to_options(str(out.get("effort")), opts, model=model)
    # 无档位时保留原 effort 字符串（请求侧再归一）；勿强行改成 medium 抹掉 max
    return out
