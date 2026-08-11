from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from app.config import (
    CHAIN_MODEL_SETTING_KEYS,
    CHAIN_SEARCH_SETTING_KEYS,
    EDITABLE_SETTING_KEYS,
    LEGACY_SEARCH_SECRET_KEYS,
    SECRET_SETTING_KEYS,
    Settings,
)
from app.engine.web.search_providers import (
    mask_search_providers,
    migrate_search_providers,
    validate_search_providers_unique,
)
from app.models.candidate import (
    mask_candidates,
    migrate_settings_dict,
    sync_legacy_aliases,
)
from app.models.catalog import enrich_candidate_dict

__all__ = [
    "EDITABLE_SETTING_KEYS",
    "PLACEHOLDER_API_KEYS",
    "SECRET_SETTING_KEYS",
    "SettingsStore",
    "is_llm_api_key_configured",
    "load_effective_settings",
]

# 与历史 .env.example / 默认 Settings 占位一致；勿把真实密钥形态写进此处
PLACEHOLDER_API_KEYS = frozenset({"", "sk-none", "sk-your-key"})


def is_llm_api_key_configured(key: str | None) -> bool:
    return (key or "").strip() not in PLACEHOLDER_API_KEYS


def _mask(value: str | None) -> str | None:
    if not value:
        return value
    if len(value) <= 4:
        return "****"
    return f"{value[:2]}***{value[-4:]}"


def _enrich_chains(data: dict) -> dict:
    out = dict(data)
    for key in CHAIN_MODEL_SETTING_KEYS:
        raw = out.get(key)
        if not isinstance(raw, list):
            continue
        out[key] = [
            enrich_candidate_dict(item) if isinstance(item, dict) else item for item in raw
        ]
    return out


def _normalize_model_settings(data: dict) -> dict:
    """migrate → enrich → sync_legacy 单一管线（含搜索链）。"""
    out = migrate_settings_dict(dict(data))
    out = _enrich_chains(out)
    out = sync_legacy_aliases(out)
    return migrate_search_providers(out)


def load_effective_settings(base: Settings | None = None) -> Settings:
    """.env / 环境变量为底，再叠知识库 `.kb/settings.json`。"""
    root = base if base is not None else Settings()
    return SettingsStore(root.kb_path, root).get()


class SettingsStore:
    def __init__(self, kb_path: Path, base: Settings) -> None:
        self._kb_path = Path(kb_path)
        self._base = base
        self._path = self._kb_path / ".kb" / "settings.json"
        self._overrides: dict = self._load_overrides()
        # 启动时若仅有 legacy 字段，迁移进 chat/utility/search 链并落盘
        migrated = migrate_settings_dict(dict(self._overrides))
        migrated = migrate_search_providers({**self._base.model_dump(), **migrated})
        need_write = False
        if migrated != self._overrides and (
            "chat_models" in migrated or "utility_models" in migrated
        ):
            if not self._overrides.get("chat_models") and migrated.get("chat_models"):
                need_write = True
            if not self._overrides.get("utility_models") and migrated.get("utility_models"):
                need_write = True
        if (
            "search_providers" not in self._overrides
            and migrated.get("search_providers")
        ):
            need_write = True
        if need_write:
            full = _normalize_model_settings({**self._base.model_dump(), **self._overrides})
            for key in (
                "chat_models",
                "utility_models",
                "big_model",
                "small_model",
                "big_base_url",
                "small_base_url",
                "big_api_key",
                "small_api_key",
                "search_providers",
                "tavily_api_key",
                "serper_api_key",
                "brave_search_api_key",
                "search_provider_order",
            ):
                if key in full and key in EDITABLE_SETTING_KEYS:
                    self._overrides[key] = full[key]
            self._write_overrides(self._overrides)
        self._current = self._build_settings(self._overrides)

    def _load_overrides(self) -> dict:
        if not self._path.is_file():
            return {}
        data = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return {
            key: value
            for key, value in data.items()
            if key in EDITABLE_SETTING_KEYS
        }

    def _build_settings(self, overrides: dict) -> Settings:
        merged = _normalize_model_settings({**self._base.model_dump(), **overrides})
        merged["kb_path"] = self._kb_path
        return Settings.model_validate(merged)

    def get(self) -> Settings:
        return self._current

    def public_dict(self) -> dict:
        data = self._current.model_dump(mode="json")
        configured = is_llm_api_key_configured(self._current.openai_api_key)
        data["llm_api_key_configured"] = configured
        for key in SECRET_SETTING_KEYS | LEGACY_SEARCH_SECRET_KEYS:
            if key not in data:
                continue
            if key == "openai_api_key" and not configured:
                data[key] = None
            else:
                data[key] = _mask(data[key])
        for key in CHAIN_MODEL_SETTING_KEYS:
            if key in data:
                data[key] = mask_candidates(data[key])
        for key in CHAIN_SEARCH_SETTING_KEYS:
            if key in data:
                data[key] = mask_search_providers(data[key])
        return data

    def _write_overrides(self, overrides: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(overrides, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self._path)

    def update(self, patch: dict) -> Settings:
        if "kb_path" in patch:
            raise ValueError("kb_path is not editable")

        filtered: dict = {}
        for key, value in patch.items():
            if key not in EDITABLE_SETTING_KEYS:
                continue
            if key in SECRET_SETTING_KEYS | LEGACY_SEARCH_SECRET_KEYS:
                if value == "" or value is None:
                    # "" / null = 不修改（前端未改密钥时常传 null）
                    continue
                filtered[key] = value
                continue
            if key in CHAIN_MODEL_SETTING_KEYS and isinstance(value, list):
                prev = self._overrides.get(key) or self._current.model_dump().get(key) or []
                prev_by_id = {
                    (c.get("id") if isinstance(c, dict) else None): c
                    for c in prev
                    if isinstance(c, dict)
                }
                merged_list = []
                for item in value:
                    if not isinstance(item, dict):
                        continue
                    item = enrich_candidate_dict(dict(item))
                    use_custom = item.pop("use_custom_endpoint", None)
                    old = prev_by_id.get(item.get("id"))
                    if use_custom is False:
                        # 回到默认端点：清空候选级 URL / Key
                        item["base_url"] = None
                        item["api_key"] = None
                    else:
                        api_key = item.get("api_key")
                        if old and (
                            api_key is None
                            or api_key == ""
                            or (isinstance(api_key, str) and "***" in api_key)
                        ):
                            item["api_key"] = old.get("api_key")
                    merged_list.append(item)
                filtered[key] = merged_list
                continue
            if key in CHAIN_SEARCH_SETTING_KEYS and isinstance(value, list):
                validate_search_providers_unique(value)
                prev = self._overrides.get(key) or self._current.model_dump().get(key) or []
                prev_by_id = {
                    (c.get("id") if isinstance(c, dict) else None): c
                    for c in prev
                    if isinstance(c, dict)
                }
                prev_by_provider = {
                    (c.get("provider") if isinstance(c, dict) else None): c
                    for c in prev
                    if isinstance(c, dict)
                }
                merged_list = []
                for item in value:
                    if not isinstance(item, dict):
                        continue
                    item = dict(item)
                    provider = str(item.get("provider") or "").strip().lower()
                    item["provider"] = provider
                    item["id"] = str(item.get("id") or provider).strip() or provider
                    old = prev_by_id.get(item.get("id")) or prev_by_provider.get(provider)
                    api_key = item.get("api_key")
                    if old and (
                        api_key is None
                        or api_key == ""
                        or (isinstance(api_key, str) and "***" in api_key)
                    ):
                        item["api_key"] = old.get("api_key")
                    merged_list.append(item)
                filtered[key] = merged_list
                continue
            filtered[key] = value

        merged_overrides = {**self._overrides, **filtered}

        # 仅改 legacy 别名时，同步到对应链的首个候选
        merged_overrides = self._propagate_legacy_to_chains(merged_overrides, filtered)

        full = _normalize_model_settings({**self._base.model_dump(), **merged_overrides})
        merged_overrides = {
            k: v for k, v in full.items() if k in EDITABLE_SETTING_KEYS
        }
        search_chain_updated = "search_providers" in filtered
        for k in SECRET_SETTING_KEYS | LEGACY_SEARCH_SECRET_KEYS:
            # 搜索链已更新：以 sync_legacy 结果为准，勿用旧 overrides 复活密钥
            if search_chain_updated and k in LEGACY_SEARCH_SECRET_KEYS:
                continue
            if k not in filtered and k in self._overrides:
                merged_overrides[k] = self._overrides[k]

        try:
            new_settings = self._build_settings(merged_overrides)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc

        self._overrides = merged_overrides
        self._current = new_settings
        self._write_overrides(self._overrides)
        return self._current

    @staticmethod
    def _propagate_legacy_to_chains(overrides: dict, filtered: dict) -> dict:
        out = dict(overrides)
        mapping = [
            ("big_model", "big_base_url", "big_api_key", "chat_models"),
            ("small_model", "small_base_url", "small_api_key", "utility_models"),
        ]
        for model_k, url_k, key_k, chain_k in mapping:
            if not any(k in filtered for k in (model_k, url_k, key_k)):
                continue
            if chain_k in filtered:
                continue
            chain = list(out.get(chain_k) or [])
            if not chain:
                item = enrich_candidate_dict(
                    {
                        "model": out.get(model_k) or "gpt-4o",
                        "base_url": out.get(url_k),
                        "api_key": out.get(key_k),
                    }
                )
                out[chain_k] = [item]
                continue
            head = dict(chain[0]) if isinstance(chain[0], dict) else {}
            if model_k in filtered:
                head["model"] = filtered[model_k]
            if url_k in filtered:
                head["base_url"] = filtered[url_k]
            if key_k in filtered:
                head["api_key"] = filtered[key_k]
            head = enrich_candidate_dict(head)
            out[chain_k] = [head, *chain[1:]]
        return out
