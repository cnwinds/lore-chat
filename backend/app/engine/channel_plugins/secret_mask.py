"""通道 secret 脱敏：对齐 settings.json（空/掩码不覆盖）。"""

from __future__ import annotations


def is_masked_or_empty(value: str | None) -> bool:
    raw = (value or "").strip()
    if not raw:
        return True
    return "***" in raw or raw in {"****", "••••", "••••••••"}


def mask_secret(value: str | None) -> str | None:
    if not value:
        return value
    if len(value) <= 4:
        return "****"
    return f"{value[:2]}***{value[-4:]}"


def merge_secrets(
    stored: dict[str, str] | None,
    incoming: dict[str, str] | None,
) -> dict[str, str]:
    out = dict(stored or {})
    for key, raw in (incoming or {}).items():
        if not isinstance(key, str) or not key:
            continue
        if not isinstance(raw, str) or is_masked_or_empty(raw):
            continue
        out[key] = raw
    return out


# 哈希与可复制明文都不进列表回包；明文只经 Cookie 鉴权的 credential 接口取出。
_PRIVATE_SECRET_KEYS = {"key_hash", "key_plaintext"}


def public_secrets(secrets: dict | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, raw in (secrets or {}).items():
        if key in _PRIVATE_SECRET_KEYS:
            continue
        if not isinstance(raw, str) or not raw:
            continue
        masked = mask_secret(raw)
        if masked:
            out[key] = masked
    return out
