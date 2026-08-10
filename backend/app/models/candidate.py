"""模型候选与 chat/utility 链解析（含 small/big 一次性迁移）。"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, field_validator

Effort = Literal["low", "medium", "high"]
ImageWire = Literal["data", "url"]
ThinkingProtocol = Literal["none", "openai_kwargs", "deepseek", "qwen", "agnes"]
ModelChain = Literal["chat", "utility"]


class ModelCandidate(BaseModel):
    id: str = ""
    model: str
    base_url: str | None = None
    api_key: str | None = None
    image: bool = False
    thinking: bool = False
    effort: Effort = "medium"
    image_wire: ImageWire = "data"
    thinking_protocol: ThinkingProtocol = "none"

    @field_validator("id", mode="before")
    @classmethod
    def _empty_id(cls, v: Any) -> str:
        if v is None or (isinstance(v, str) and not v.strip()):
            return ""
        return str(v).strip()

    def ensure_id(self) -> ModelCandidate:
        if self.id:
            return self
        return self.model_copy(update={"id": uuid.uuid4().hex[:12]})


def _legacy_candidate(
    *,
    model: str,
    base_url: str | None,
    api_key: str | None,
    chain: ModelChain,
) -> ModelCandidate:
    from app.models.catalog import lookup_capabilities

    caps = lookup_capabilities(model, base_url)
    return ModelCandidate(
        id=f"{chain}-migrated",
        model=model,
        base_url=base_url,
        api_key=api_key,
        image=caps.image,
        thinking=caps.thinking,
        effort="medium",
        image_wire=caps.image_wire,
        thinking_protocol=caps.thinking_protocol,
    ).ensure_id()


def parse_candidates(raw: Any) -> list[ModelCandidate]:
    if not raw:
        return []
    if isinstance(raw, str):
        import json

        raw = json.loads(raw)
    if not isinstance(raw, list):
        return []
    out: list[ModelCandidate] = []
    for item in raw:
        if isinstance(item, ModelCandidate):
            out.append(item.ensure_id())
        elif isinstance(item, dict):
            out.append(ModelCandidate.model_validate(item).ensure_id())
    return out


def resolve_chain_candidates(settings: Any, chain: ModelChain) -> list[ModelCandidate]:
    """返回有序候选；空链时从 legacy small/big 合成一条。"""
    if chain == "chat":
        configured = parse_candidates(getattr(settings, "chat_models", None))
        if configured:
            return configured
        return [
            _legacy_candidate(
                model=getattr(settings, "big_model", "gpt-4o"),
                base_url=getattr(settings, "big_base_url", None),
                api_key=getattr(settings, "big_api_key", None),
                chain="chat",
            )
        ]
    configured = parse_candidates(getattr(settings, "utility_models", None))
    if configured:
        return configured
    return [
        _legacy_candidate(
            model=getattr(settings, "small_model", "gpt-4o-mini"),
            base_url=getattr(settings, "small_base_url", None),
            api_key=getattr(settings, "small_api_key", None),
            chain="utility",
        )
    ]


def migrate_settings_dict(data: dict[str, Any]) -> dict[str, Any]:
    """将旧 small/big 字段一次性写入 chat_models/utility_models（若尚无新字段）。"""
    out = dict(data)
    if not parse_candidates(out.get("chat_models")):
        big = out.get("big_model") or "gpt-4o"
        out["chat_models"] = [
            _legacy_candidate(
                model=str(big),
                base_url=out.get("big_base_url"),
                api_key=out.get("big_api_key"),
                chain="chat",
            ).model_dump()
        ]
    if not parse_candidates(out.get("utility_models")):
        small = out.get("small_model") or "gpt-4o-mini"
        out["utility_models"] = [
            _legacy_candidate(
                model=str(small),
                base_url=out.get("small_base_url"),
                api_key=out.get("small_api_key"),
                chain="utility",
            ).model_dump()
        ]
    return out


def sync_legacy_aliases(settings_dict: dict[str, Any]) -> dict[str, Any]:
    """链首候选回写 small/big 别名，兼容仍读旧字段的代码/测试。"""
    out = dict(settings_dict)
    chat = parse_candidates(out.get("chat_models"))
    util = parse_candidates(out.get("utility_models"))
    if chat:
        c0 = chat[0]
        out["big_model"] = c0.model
        out["big_base_url"] = c0.base_url
        if c0.api_key is not None:
            out["big_api_key"] = c0.api_key
    if util:
        u0 = util[0]
        out["small_model"] = u0.model
        out["small_base_url"] = u0.base_url
        if u0.api_key is not None:
            out["small_api_key"] = u0.api_key
    return out


def mask_candidates(raw: Any) -> list[dict[str, Any]]:
    cands = parse_candidates(raw)
    masked: list[dict[str, Any]] = []
    for c in cands:
        d = c.model_dump()
        key = d.get("api_key")
        if key:
            if len(key) <= 4:
                d["api_key"] = "****"
            else:
                d["api_key"] = f"{key[:2]}***{key[-4:]}"
        masked.append(d)
    return masked


# 改配置清 disabled：只比「路由身份」字段，不含 effort/thinking*（enrich 默认易误触）
_ROUTING_CANDIDATE_KEYS = ("id", "model", "base_url", "api_key", "image", "image_wire")
_ROUTING_SETTINGS_KEYS = (
    "openai_api_key",
    "openai_base_url",
    "big_api_key",
    "big_base_url",
    "big_model",
    "small_api_key",
    "small_base_url",
    "small_model",
    "public_base_url",
)


def model_routing_fingerprint(settings: Any) -> str:
    """链身份 + 密钥/端点/公网基址指纹（供配置变更是否清 disabled）。"""
    import json

    def chain_rows(items: list | None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for c in items or []:
            if not isinstance(c, dict):
                continue
            rows.append({k: c.get(k) for k in _ROUTING_CANDIDATE_KEYS})
        return rows

    payload: dict[str, Any] = {
        "chat_models": chain_rows(getattr(settings, "chat_models", None)),
        "utility_models": chain_rows(getattr(settings, "utility_models", None)),
    }
    for k in _ROUTING_SETTINGS_KEYS:
        payload[k] = getattr(settings, k, None)
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def model_routing_changed(prev: Any, new: Any) -> bool:
    return model_routing_fingerprint(prev) != model_routing_fingerprint(new)
