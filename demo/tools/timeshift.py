"""把定稿时的绝对时间戳整体平移到「距今多少天」的当前时间。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any


def compute_offset_days(reference_date: str, today: date) -> int:
    return (today - date.fromisoformat(reference_date)).days


def shift_iso_timestamp(value: str, offset_days: int) -> str:
    if not value or offset_days == 0:
        return value
    raw = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return value
    return (parsed + timedelta(days=offset_days)).isoformat()


def shift_in_place(obj: Any, offset_days: int, keys: set[str]) -> Any:
    if offset_days == 0:
        return obj
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in keys and isinstance(value, str):
                obj[key] = shift_iso_timestamp(value, offset_days)
            else:
                shift_in_place(value, offset_days, keys)
    elif isinstance(obj, list):
        for item in obj:
            shift_in_place(item, offset_days, keys)
    return obj
