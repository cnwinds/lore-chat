"""搜索提供商有序链：解析、迁移、脱敏、路由指纹。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SEARCH_PROVIDER_TYPES = frozenset({"tavily", "serper", "brave"})

_LEGACY_KEY_BY_PROVIDER: dict[str, str] = {
    "tavily": "tavily_api_key",
    "serper": "serper_api_key",
    "brave": "brave_search_api_key",
}

_DEFAULT_ORDER = ("tavily", "serper", "brave")


@dataclass(frozen=True)
class SearchProviderEntry:
    id: str
    provider: str
    api_key: str | None = None

    def model_dump(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "provider": self.provider,
            "api_key": self.api_key,
        }


def parse_search_providers(raw: Any) -> list[SearchProviderEntry]:
    """解析链；非法项跳过；同一 provider 只保留首次出现。"""
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        import json

        raw = json.loads(raw)
    if not isinstance(raw, list):
        return []

    seen: set[str] = set()
    out: list[SearchProviderEntry] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        provider = str(item.get("provider") or "").strip().lower()
        if provider not in SEARCH_PROVIDER_TYPES or provider in seen:
            continue
        seen.add(provider)
        cid = str(item.get("id") or provider).strip() or provider
        key = item.get("api_key")
        api_key = None if key is None else str(key)
        if api_key is not None and not api_key.strip():
            api_key = None
        out.append(SearchProviderEntry(id=cid, provider=provider, api_key=api_key))
    return out


class DuplicateSearchProviderError(ValueError):
    def __init__(self, provider: str):
        self.provider = provider
        super().__init__(f"duplicate search provider: {provider}")


def validate_search_providers_unique(raw: Any) -> None:
    """保存前校验：非法类型或重复 provider 抛 DuplicateSearchProviderError / ValueError。"""
    if raw is None or raw == "":
        return
    if not isinstance(raw, list):
        raise ValueError("search_providers must be a list")
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("search_providers items must be objects")
        provider = str(item.get("provider") or "").strip().lower()
        if provider not in SEARCH_PROVIDER_TYPES:
            raise ValueError(f"unknown search provider: {provider or '(empty)'}")
        if provider in seen:
            raise DuplicateSearchProviderError(provider)
        seen.add(provider)


def mask_search_providers(raw: Any) -> list[dict[str, Any]]:
    masked: list[dict[str, Any]] = []
    for e in parse_search_providers(raw):
        d = e.model_dump()
        key = d.get("api_key")
        if key:
            if len(key) <= 4:
                d["api_key"] = "****"
            else:
                d["api_key"] = f"{key[:2]}***{key[-4:]}"
        masked.append(d)
    return masked


def _legacy_key(settings_or_dict: Any, provider: str) -> str | None:
    field = _LEGACY_KEY_BY_PROVIDER[provider]
    if isinstance(settings_or_dict, dict):
        val = settings_or_dict.get(field)
    else:
        val = getattr(settings_or_dict, field, None)
    if val is None:
        return None
    s = str(val).strip()
    return s or None


def _order_from_settings(data: dict[str, Any]) -> list[str]:
    raw = data.get("search_provider_order") or ",".join(_DEFAULT_ORDER)
    names = [p.strip().lower() for p in str(raw).split(",")]
    out: list[str] = []
    for n in names:
        if n in SEARCH_PROVIDER_TYPES and n not in out:
            out.append(n)
    for n in _DEFAULT_ORDER:
        if n not in out:
            out.append(n)
    return out


def migrate_search_providers(data: dict[str, Any]) -> dict[str, Any]:
    """合成 search_providers。

    - 若 dict 含 `search_providers` 且为 list（含 `[]`）：以链为准并回写 legacy。
    - 若键缺失或值为 None：从旧三密钥 + order 迁移。
    """
    out = dict(data)
    raw = out.get("search_providers", None)
    # 键存在且为 list（含空）→ 显式链；None / 缺省 → 迁移
    if "search_providers" in out and isinstance(raw, list):
        existing = parse_search_providers(raw)
        out["search_providers"] = [e.model_dump() for e in existing]
        return sync_legacy_search_aliases(out)

    chain: list[dict[str, Any]] = []
    for provider in _order_from_settings(out):
        key = _legacy_key(out, provider)
        if not key:
            continue
        chain.append({"id": provider, "provider": provider, "api_key": key})
    out["search_providers"] = chain
    return sync_legacy_search_aliases(out)


def legacy_search_entries_from_aliases(data: dict[str, Any]) -> list[SearchProviderEntry]:
    """仅从旧三密钥构造条目（不写回）；供 Settings 默认空链时的 .env/测试兼容。"""
    chain: list[dict[str, Any]] = []
    for provider in _order_from_settings(data):
        key = _legacy_key(data, provider)
        if not key:
            continue
        chain.append({"id": provider, "provider": provider, "api_key": key})
    return parse_search_providers(chain)


def sync_legacy_search_aliases(settings_dict: dict[str, Any]) -> dict[str, Any]:
    """链回写旧三字段与 order，兼容仍读旧字段的代码。"""
    out = dict(settings_dict)
    entries = parse_search_providers(out.get("search_providers"))
    by_provider = {e.provider: e for e in entries}
    for provider, field in _LEGACY_KEY_BY_PROVIDER.items():
        e = by_provider.get(provider)
        out[field] = e.api_key if e else None
    out["search_provider_order"] = (
        ",".join(e.provider for e in entries) if entries else ",".join(_DEFAULT_ORDER)
    )
    return out


def search_routing_fingerprint(settings: Any) -> str:
    import json

    rows: list[dict[str, Any]] = []
    raw = getattr(settings, "search_providers", None)
    if raw is None and isinstance(settings, dict):
        raw = settings.get("search_providers")
    for e in parse_search_providers(raw):
        rows.append({"id": e.id, "provider": e.provider, "api_key": e.api_key})
    return json.dumps({"search_providers": rows}, sort_keys=True, ensure_ascii=False)


def search_routing_changed(prev: Any, new: Any) -> bool:
    return search_routing_fingerprint(prev) != search_routing_fingerprint(new)
