from __future__ import annotations

import copy

from app.config import (
    CHAIN_IMAGE_SETTING_KEYS,
    CHAIN_MODEL_SETTING_KEYS,
    CHAIN_SEARCH_SETTING_KEYS,
    LEGACY_SEARCH_SECRET_KEYS,
    SECRET_SETTING_KEYS,
)

FULL_MASK = "***"

_CHAIN_KEYS = CHAIN_MODEL_SETTING_KEYS | CHAIN_SEARCH_SETTING_KEYS | CHAIN_IMAGE_SETTING_KEYS
_TOP_LEVEL_KEYS = SECRET_SETTING_KEYS | LEGACY_SEARCH_SECRET_KEYS


def redact_secrets_for_guest(data: dict) -> dict:
    """把设置里的全部密钥换成常量遮罩，不保留任何真实片段。"""
    out = copy.deepcopy(data)
    for key in _TOP_LEVEL_KEYS:
        if out.get(key) is not None:
            out[key] = FULL_MASK
    for key in _CHAIN_KEYS:
        chain = out.get(key)
        if not isinstance(chain, list):
            continue
        for item in chain:
            if isinstance(item, dict) and item.get("api_key") is not None:
                item["api_key"] = FULL_MASK
    return out
