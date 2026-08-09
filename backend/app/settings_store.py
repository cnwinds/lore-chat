from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from app.config import (
    EDITABLE_SETTING_KEYS,
    SECRET_SETTING_KEYS,
    Settings,
)

__all__ = [
    "EDITABLE_SETTING_KEYS",
    "SECRET_SETTING_KEYS",
    "SettingsStore",
    "load_effective_settings",
]


def _mask(value: str | None) -> str | None:
    if not value:
        return value
    if len(value) <= 4:
        return "****"
    return f"{value[:2]}***{value[-4:]}"


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
        merged = self._base.model_dump()
        merged.update(overrides)
        merged["kb_path"] = self._kb_path
        return Settings.model_validate(merged)

    def get(self) -> Settings:
        return self._current

    def public_dict(self) -> dict:
        data = self._current.model_dump(mode="json")
        for key in SECRET_SETTING_KEYS:
            if key in data:
                data[key] = _mask(data[key])
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
            if key in SECRET_SETTING_KEYS and (value is None or value == ""):
                continue
            filtered[key] = value

        merged_overrides = {**self._overrides, **filtered}
        try:
            new_settings = self._build_settings(merged_overrides)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc

        self._overrides = merged_overrides
        self._current = new_settings
        self._write_overrides(self._overrides)
        return self._current
