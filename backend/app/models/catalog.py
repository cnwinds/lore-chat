"""模型能力目录：本地 preset + models.dev 在线目录；未命中保守默认。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.candidate import ImageWire, ThinkingProtocol
from app.models.effort import Effort, default_effort, supported_efforts
from app.models.models_dev import (
    CatalogHit,
    ModelsDevStore,
    infer_image_wire,
    infer_thinking_protocol,
)


@dataclass(frozen=True)
class ModelCapabilities:
    image: bool = False
    thinking: bool = False
    image_wire: ImageWire = "data"
    thinking_protocol: ThinkingProtocol = "none"
    effort: Effort = "medium"
    effort_options: tuple[Effort, ...] = ("low", "medium", "high")
    source: str = "default"  # preset|models_dev|prefix|default


def _with_efforts(
    *,
    model: str,
    image: bool,
    thinking: bool,
    image_wire: ImageWire,
    thinking_protocol: ThinkingProtocol,
    source: str,
) -> ModelCapabilities:
    opts = supported_efforts(model, thinking_protocol)
    return ModelCapabilities(
        image=image,
        thinking=thinking,
        image_wire=image_wire,
        thinking_protocol=thinking_protocol,
        effort=default_effort(model, thinking_protocol),
        effort_options=opts,
        source=source,
    )


# 常用模型保守预填（优先于在线目录，补齐 Agnes url 等）
_PRESET: dict[str, ModelCapabilities] = {
    "agnes-2.0-flash": _with_efforts(
        model="agnes-2.0-flash",
        image=True,
        thinking=True,
        image_wire="url",
        thinking_protocol="agnes",
        source="preset",
    ),
    "agnes-2.5-flash": _with_efforts(
        model="agnes-2.5-flash",
        image=True,
        thinking=True,
        image_wire="url",
        thinking_protocol="agnes",
        source="preset",
    ),
    "agnes-2.5-pro": _with_efforts(
        model="agnes-2.5-pro",
        image=True,
        thinking=True,
        image_wire="url",
        thinking_protocol="agnes",
        source="preset",
    ),
    "agnes-2.5-pro-alpha": _with_efforts(
        model="agnes-2.5-pro-alpha",
        image=True,
        thinking=True,
        image_wire="url",
        thinking_protocol="agnes",
        source="preset",
    ),
    "deepseek-chat": _with_efforts(
        model="deepseek-chat",
        image=False,
        thinking=True,
        image_wire="data",
        thinking_protocol="deepseek",
        source="preset",
    ),
    "deepseek-reasoner": _with_efforts(
        model="deepseek-reasoner",
        image=False,
        thinking=True,
        image_wire="data",
        thinking_protocol="deepseek",
        source="preset",
    ),
    "deepseek-v4-flash": _with_efforts(
        model="deepseek-v4-flash",
        image=False,
        thinking=True,
        image_wire="data",
        thinking_protocol="deepseek",
        source="preset",
    ),
    "deepseek-v4-pro": _with_efforts(
        model="deepseek-v4-pro",
        image=False,
        thinking=True,
        image_wire="data",
        thinking_protocol="deepseek",
        source="preset",
    ),
    "qwen3.8-max": _with_efforts(
        model="qwen3.8-max",
        image=True,
        thinking=True,
        image_wire="data",
        thinking_protocol="qwen",
        source="preset",
    ),
    "qwen3-max": _with_efforts(
        model="qwen3-max",
        image=True,
        thinking=True,
        image_wire="data",
        thinking_protocol="qwen",
        source="preset",
    ),
    "qwen-plus": _with_efforts(
        model="qwen-plus",
        image=True,
        thinking=True,
        image_wire="data",
        thinking_protocol="qwen",
        source="preset",
    ),
    "gpt-4o": _with_efforts(
        model="gpt-4o",
        image=True,
        thinking=False,
        image_wire="data",
        thinking_protocol="none",
        source="preset",
    ),
    "gpt-4o-mini": _with_efforts(
        model="gpt-4o-mini",
        image=True,
        thinking=False,
        image_wire="data",
        thinking_protocol="none",
        source="preset",
    ),
    "gpt-4.1": _with_efforts(
        model="gpt-4.1",
        image=True,
        thinking=False,
        image_wire="data",
        thinking_protocol="none",
        source="preset",
    ),
    "o3": _with_efforts(
        model="o3",
        image=True,
        thinking=True,
        image_wire="data",
        thinking_protocol="openai_kwargs",
        source="preset",
    ),
    "o4-mini": _with_efforts(
        model="o4-mini",
        image=True,
        thinking=True,
        image_wire="data",
        thinking_protocol="openai_kwargs",
        source="preset",
    ),
    "gpt-5.2": _with_efforts(
        model="gpt-5.2",
        image=True,
        thinking=True,
        image_wire="data",
        thinking_protocol="openai_kwargs",
        source="preset",
    ),
}


def _normalize_model_id(model: str) -> str:
    return (model or "").strip().lower()


def _from_hit(hit: CatalogHit) -> ModelCapabilities:
    opts = hit.effort_options or supported_efforts(hit.id, hit.thinking_protocol)
    effort = hit.effort if hit.effort in opts else default_effort(hit.id, hit.thinking_protocol)
    return ModelCapabilities(
        image=hit.image,
        thinking=hit.thinking,
        image_wire=hit.image_wire,
        thinking_protocol=hit.thinking_protocol,
        effort=effort,
        effort_options=opts,
        source="models_dev",
    )


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
    mid = _normalize_model_id(model)
    # preset：精确 id；gpt-5.2-* 等走前缀
    if mid in _PRESET:
        return _PRESET[mid]
    if mid.startswith("gpt-5.2"):
        return _with_efforts(
            model=mid,
            image=True,
            thinking=True,
            image_wire="data",
            thinking_protocol="openai_kwargs",
            source="preset",
        )

    if models_dev is not None:
        hit = models_dev.lookup(mid)
        if hit is not None:
            return _from_hit(hit)

    prefixed = _prefix_caps(model, base_url)
    if prefixed is not None:
        return prefixed
    return ModelCapabilities()


# 进程级可选注入（admin / enrich 共用）
_ACTIVE_STORE: ModelsDevStore | None = None


def set_active_models_dev_store(store: ModelsDevStore | None) -> None:
    global _ACTIVE_STORE
    _ACTIVE_STORE = store


def get_active_models_dev_store() -> ModelsDevStore | None:
    return _ACTIVE_STORE


def enrich_candidate_dict(item: dict[str, Any]) -> dict[str, Any]:
    """能力预填；thinking_protocol / 缺省能力随目录自适应。"""
    from app.models.effort import coerce_effort

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
        out["effort"] = coerce_effort(
            str(out.get("effort")),
            model=model,
            protocol=caps.thinking_protocol,
        )
    return out
