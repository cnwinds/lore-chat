"""模型候选与 chat/utility 链解析（含 small/big 一次性迁移）。"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.models.effort import Effort, coerce_effort, coerce_to_options, default_effort

ImageWire = Literal["data", "url"]
VideoWire = Literal["data", "url"]
ThinkingProtocol = Literal["none", "openai_kwargs", "deepseek", "qwen", "agnes"]
ModelChain = Literal["chat", "utility", "embed"]

# 兼容旧 import：from app.models.candidate import Effort
__all__ = [
    "Effort",
    "ImageWire",
    "VideoWire",
    "ThinkingProtocol",
    "ModelChain",
    "ModelCandidate",
]


class ModelCandidate(BaseModel):
    id: str = ""
    model: str
    base_url: str | None = None
    api_key: str | None = None
    # 厂家预设 id（openai/zhipu/.../custom）；仅设置 UI，运行时路由不依赖
    provider: str | None = None
    image: bool = False
    video: bool = False
    thinking: bool = False
    image_wire: ImageWire = "data"
    video_wire: VideoWire = "data"
    max_videos: int = 1
    max_images: int | None = None
    thinking_protocol: ThinkingProtocol = "none"
    # 空列表 = 无对外强度档（如 Agnes）；展示/校验以此为准，勿仅靠 live 目录
    effort_options: list[str] = Field(default_factory=list)
    effort: Effort = "medium"

    @field_validator("id", mode="before")
    @classmethod
    def _empty_id(cls, v: Any) -> str:
        if v is None or (isinstance(v, str) and not v.strip()):
            return ""
        return str(v).strip()

    @field_validator("effort_options", mode="before")
    @classmethod
    def _coerce_effort_options(cls, v: Any) -> list[str]:
        if not v:
            return []
        if isinstance(v, (list, tuple)):
            return [str(x).strip() for x in v if str(x).strip()]
        return []

    @field_validator("effort", mode="before")
    @classmethod
    def _coerce_effort_field(cls, v: Any, info) -> str:
        data = info.data if hasattr(info, "data") else {}
        model = str((data or {}).get("model") or "")
        protocol = str((data or {}).get("thinking_protocol") or "none")
        opts = (data or {}).get("effort_options") or []
        if opts:
            return coerce_to_options(
                str(v) if v is not None else None,
                tuple(opts),
                model=model,
            )
        return coerce_effort(str(v) if v is not None else None, model=model, protocol=protocol)

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
        video=caps.video,
        thinking=caps.thinking,
        effort=default_effort(model, caps.thinking_protocol),
        effort_options=list(caps.effort_options),
        image_wire=caps.image_wire,
        video_wire=caps.video_wire,
        max_videos=caps.max_videos,
        max_images=caps.max_images,
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


def _legacy_model_name(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _explicit_model_chain(data: dict[str, Any], key: str) -> bool:
    """settings.json / patch 里出现的 list（含 []）视为用户明确配置，禁止再用 legacy 名回填。"""
    return key in data and isinstance(data.get(key), list)


def resolve_chain_candidates(settings: Any, chain: ModelChain) -> list[ModelCandidate]:
    """返回有序候选；空链且无 legacy 模型名时保持为空。

    不在运行时用全局 openai_* 回填：每条候选须自带 base_url / api_key
    （旧配置由 migrate_settings_dict 一次性提升）。
    不因类默认值注入 gpt-4o 等占位模型。
    """
    if chain == "chat":
        configured = parse_candidates(getattr(settings, "chat_models", None))
        if configured:
            return configured
        model = _legacy_model_name(getattr(settings, "big_model", None))
        if not model:
            return []
        return [
            _legacy_candidate(
                model=model,
                base_url=getattr(settings, "big_base_url", None),
                api_key=getattr(settings, "big_api_key", None),
                chain="chat",
            )
        ]
    if chain == "embed":
        configured = parse_candidates(getattr(settings, "embed_models", None))
        if configured:
            return configured
        model = _legacy_model_name(getattr(settings, "embed_model", None))
        if not model:
            return []
        return [
            ModelCandidate(
                id="embed-legacy",
                model=model,
                base_url=getattr(settings, "embed_base_url", None),
                api_key=getattr(settings, "embed_api_key", None),
                image=False,
                thinking=False,
                effort_options=[],
                thinking_protocol="none",
            ).ensure_id()
        ]
    configured = parse_candidates(getattr(settings, "utility_models", None))
    if configured:
        return configured
    model = _legacy_model_name(getattr(settings, "small_model", None))
    if not model:
        return []
    return [
        _legacy_candidate(
            model=model,
            base_url=getattr(settings, "small_base_url", None),
            api_key=getattr(settings, "small_api_key", None),
            chain="utility",
        )
    ]


def migrate_settings_dict(data: dict[str, Any]) -> dict[str, Any]:
    """将旧 small/big/embed 字段一次性写入对应 *_models 链（若尚无新字段）。

    键存在且为 list（含 []）= 显式链，不再用 legacy 模型名回填。
    键缺失时：仅当 legacy 模型名非空才合成一条；不注入 gpt-4o 等占位名。
    并在候选缺少 base_url/api_key 时，从全局 openai_* 填入（取消「默认端点」后的兼容）。
    """
    out = dict(data)
    if not _explicit_model_chain(out, "chat_models"):
        big = _legacy_model_name(out.get("big_model"))
        out["chat_models"] = (
            [
                _legacy_candidate(
                    model=big,
                    base_url=out.get("big_base_url"),
                    api_key=out.get("big_api_key"),
                    chain="chat",
                ).model_dump()
            ]
            if big
            else []
        )
    if not _explicit_model_chain(out, "utility_models"):
        small = _legacy_model_name(out.get("small_model"))
        out["utility_models"] = (
            [
                _legacy_candidate(
                    model=small,
                    base_url=out.get("small_base_url"),
                    api_key=out.get("small_api_key"),
                    chain="utility",
                ).model_dump()
            ]
            if small
            else []
        )
    if not _explicit_model_chain(out, "embed_models"):
        emb = _legacy_model_name(out.get("embed_model"))
        out["embed_models"] = (
            [
                ModelCandidate(
                    id="embed-migrated",
                    model=emb,
                    base_url=out.get("embed_base_url"),
                    api_key=out.get("embed_api_key"),
                    provider="custom",
                    image=False,
                    thinking=False,
                    effort_options=[],
                    thinking_protocol="none",
                )
                .ensure_id()
                .model_dump()
            ]
            if emb
            else []
        )
    return promote_global_openai_endpoint(out)


# 权威定义：settings_store 再导出同名常量
PLACEHOLDER_API_KEYS = frozenset({"", "sk-none", "sk-your-key"})


def is_placeholder_api_key(key: str | None) -> bool:
    return (key or "").strip() in PLACEHOLDER_API_KEYS


def _apply_endpoint_defaults(
    cands: list[ModelCandidate],
    *,
    global_base: str | None,
    global_key: str | None,
) -> tuple[list[ModelCandidate], bool]:
    """给缺 URL/Key 的候选补全局端点；返回 (列表, 是否有变更)。"""
    base = (global_base or "").strip() or None
    key = None if is_placeholder_api_key(global_key) else (global_key or "").strip() or None
    changed = False
    out: list[ModelCandidate] = []
    for c in cands:
        updates: dict[str, Any] = {}
        if not (c.base_url or "").strip() and base:
            updates["base_url"] = base
        if not (c.api_key or "").strip() and key:
            updates["api_key"] = key
        if updates:
            changed = True
            out.append(c.model_copy(update=updates))
        else:
            out.append(c)
    return out, changed


def promote_global_openai_endpoint(data: dict[str, Any]) -> dict[str, Any]:
    """旧配置一次性迁移：仅当 openai_* 非空时补齐缺端点的候选；运行时不再回退全局。"""
    out = dict(data)
    global_base = (out.get("openai_base_url") or "").strip() or None
    global_key = out.get("openai_api_key")
    if isinstance(global_key, str):
        global_key = global_key.strip() or None
    else:
        global_key = None
    if is_placeholder_api_key(global_key):
        global_key = None

    for chain_key in ("chat_models", "utility_models", "embed_models"):
        cands = parse_candidates(out.get(chain_key))
        if not cands:
            continue
        promoted, changed = _apply_endpoint_defaults(
            cands, global_base=global_base, global_key=global_key
        )
        if changed:
            out[chain_key] = [c.model_dump() for c in promoted]

    # 兼容仍读 legacy 字段的路径：若尚无 embed_models 提升结果，再补顶层
    embed_base = (out.get("embed_base_url") or "").strip()
    if not embed_base and global_base and not parse_candidates(out.get("embed_models")):
        out["embed_base_url"] = global_base
    embed_key = out.get("embed_api_key")
    if (
        is_placeholder_api_key(embed_key if isinstance(embed_key, str) else None)
        and global_key
        and not parse_candidates(out.get("embed_models"))
    ):
        out["embed_api_key"] = global_key
    return out


def sync_legacy_aliases(settings_dict: dict[str, Any]) -> dict[str, Any]:
    """链首候选回写 small/big/embed 别名；显式空链则清空别名，避免 env 名在运行时复活。"""
    out = dict(settings_dict)
    chat = parse_candidates(out.get("chat_models"))
    util = parse_candidates(out.get("utility_models"))
    embed = parse_candidates(out.get("embed_models"))
    if chat:
        c0 = chat[0]
        out["big_model"] = c0.model
        out["big_base_url"] = c0.base_url
        if c0.api_key is not None:
            out["big_api_key"] = c0.api_key
    elif _explicit_model_chain(out, "chat_models"):
        out["big_model"] = ""
        out["big_base_url"] = None
        out["big_api_key"] = None
    if util:
        u0 = util[0]
        out["small_model"] = u0.model
        out["small_base_url"] = u0.base_url
        if u0.api_key is not None:
            out["small_api_key"] = u0.api_key
    elif _explicit_model_chain(out, "utility_models"):
        out["small_model"] = ""
        out["small_base_url"] = None
        out["small_api_key"] = None
    if embed:
        e0 = embed[0]
        out["embed_model"] = e0.model
        out["embed_base_url"] = e0.base_url
        if e0.api_key is not None:
            out["embed_api_key"] = e0.api_key
    elif _explicit_model_chain(out, "embed_models"):
        out["embed_model"] = ""
        out["embed_base_url"] = None
        out["embed_api_key"] = None
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
    "embed_api_key",
    "embed_base_url",
    "embed_model",
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
        "embed_models": chain_rows(getattr(settings, "embed_models", None)),
    }
    for k in _ROUTING_SETTINGS_KEYS:
        payload[k] = getattr(settings, k, None)
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def model_routing_changed(prev: Any, new: Any) -> bool:
    return model_routing_fingerprint(prev) != model_routing_fingerprint(new)
