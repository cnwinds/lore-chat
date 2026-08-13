"""生图提供商有序链：解析、脱敏、路由指纹。

同一厂家（provider）可重复出现，以配置不同 model / endpoint；
唯一约束是条目 `id`。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

IMAGE_PROVIDER_TYPES = frozenset({"openai", "zhipu", "bailian"})

_DEFAULT_MODELS: dict[str, str] = {
    "openai": "dall-e-3",
    "zhipu": "cogview-4",
    "bailian": "wanx-v1",
}

_DEFAULT_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    "bailian": "https://dashscope.aliyuncs.com",
}

# 用户常把文档里的完整 POST path 贴进 base_url；运行时剥掉后缀只保留 API 根。
_ENDPOINT_SUFFIXES: tuple[str, ...] = (
    "/api/v1/services/aigc/multimodal-generation/generation",
    "/api/v1/services/aigc/image-generation/generation",
    "/api/v1/services/aigc/text2image/image-synthesis",
    "/api/v1/services/aigc/image2image/image-synthesis",
    "/images/generations",
    "/v1/images/generations",
)


def normalize_image_base_url(provider: str, raw: str | None) -> str:
    url = (raw or "").strip().rstrip("/")
    if not url:
        return _DEFAULT_BASE_URLS[provider]
    lower = url.lower()
    for suf in _ENDPOINT_SUFFIXES:
        if lower.endswith(suf):
            url = url[: -len(suf)].rstrip("/")
            break
    return url or _DEFAULT_BASE_URLS[provider]


@dataclass(frozen=True)
class ImageGenProviderEntry:
    id: str
    provider: str
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None

    def resolved_base_url(self) -> str:
        return normalize_image_base_url(self.provider, self.base_url)

    def resolved_model(self) -> str:
        raw = (self.model or "").strip()
        return raw or _DEFAULT_MODELS[self.provider]

    def model_dump(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "provider": self.provider,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "model": self.model,
        }


class DuplicateImageProviderError(ValueError):
    def __init__(self, entry_id: str):
        self.entry_id = entry_id
        super().__init__(f"duplicate image provider id: {entry_id}")


def _alloc_id(provider: str, seen_ids: set[str], preferred: str | None = None) -> str:
    cid = (preferred or "").strip() or provider
    if cid not in seen_ids:
        return cid
    if preferred:
        # 显式 id 冲突：调用方应跳过或校验失败
        return cid
    n = 2
    while f"{provider}-{n}" in seen_ids:
        n += 1
    return f"{provider}-{n}"


def parse_image_providers(raw: Any) -> list[ImageGenProviderEntry]:
    """解析链；非法项跳过；同一 id 只保留首次；同厂家可多条。"""
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        import json

        raw = json.loads(raw)
    if not isinstance(raw, list):
        return []

    seen_ids: set[str] = set()
    out: list[ImageGenProviderEntry] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        provider = str(item.get("provider") or "").strip().lower()
        if provider not in IMAGE_PROVIDER_TYPES:
            continue
        preferred = str(item.get("id") or "").strip() or None
        if preferred and preferred in seen_ids:
            continue
        cid = _alloc_id(provider, seen_ids, preferred)
        if cid in seen_ids:
            continue
        seen_ids.add(cid)
        key = item.get("api_key")
        api_key = None if key is None else str(key)
        if api_key is not None and not api_key.strip():
            api_key = None
        base_url = item.get("base_url")
        base_s = None if base_url is None else str(base_url).strip() or None
        model = item.get("model")
        model_s = None if model is None else str(model).strip() or None
        out.append(
            ImageGenProviderEntry(
                id=cid,
                provider=provider,
                api_key=api_key,
                base_url=base_s,
                model=model_s,
            )
        )
    return out


def validate_image_providers_unique(raw: Any) -> None:
    """保存前校验：厂家可重复；id 不可重复。"""
    if raw is None or raw == "":
        return
    if not isinstance(raw, list):
        raise ValueError("image_providers must be a list")
    seen_ids: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("image_providers items must be objects")
        provider = str(item.get("provider") or "").strip().lower()
        if provider not in IMAGE_PROVIDER_TYPES:
            raise ValueError(f"unknown image provider: {provider or '(empty)'}")
        cid = str(item.get("id") or provider).strip() or provider
        if cid in seen_ids:
            raise DuplicateImageProviderError(cid)
        seen_ids.add(cid)


def mask_image_providers(raw: Any) -> list[dict[str, Any]]:
    masked: list[dict[str, Any]] = []
    for e in parse_image_providers(raw):
        d = e.model_dump()
        key = d.get("api_key")
        if key:
            if len(key) <= 4:
                d["api_key"] = "****"
            else:
                d["api_key"] = f"{key[:2]}***{key[-4:]}"
        masked.append(d)
    return masked


def image_routing_fingerprint(settings: Any) -> str:
    import json

    rows: list[dict[str, Any]] = []
    raw = getattr(settings, "image_providers", None)
    if raw is None and isinstance(settings, dict):
        raw = settings.get("image_providers")
    for e in parse_image_providers(raw):
        rows.append(
            {
                "id": e.id,
                "provider": e.provider,
                "api_key": e.api_key,
                "base_url": e.base_url,
                "model": e.model,
            }
        )
    return json.dumps({"image_providers": rows}, sort_keys=True, ensure_ascii=False)


def image_routing_changed(prev: Any, new: Any) -> bool:
    return image_routing_fingerprint(prev) != image_routing_fingerprint(new)
