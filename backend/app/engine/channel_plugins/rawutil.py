"""从 raw 入站拆 instance_id / body / headers / query。"""

from __future__ import annotations

import json
from typing import Any


def as_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        try:
            parsed = json.loads(raw.decode("utf-8"))
            return parsed if isinstance(parsed, dict) else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {}
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def unwrap_raw(raw: Any) -> tuple[str, dict[str, Any], dict[str, str], dict[str, str]]:
    if isinstance(raw, tuple) and len(raw) == 2:
        return str(raw[0] or ""), as_dict(raw[1]), {}, {}
    data = as_dict(raw)
    instance_id = str(data.get("instance_id") or "").strip()
    headers = data.get("headers") if isinstance(data.get("headers"), dict) else {}
    query = data.get("query") if isinstance(data.get("query"), dict) else {}
    if "body" in data:
        body = data.get("body")
        if isinstance(body, dict):
            return instance_id, body, _str_map(headers), _str_map(query)
        return instance_id, as_dict(body), _str_map(headers), _str_map(query)
    return instance_id, data, _str_map(headers), _str_map(query)


def _str_map(raw: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in raw.items():
        if value is None:
            continue
        out[str(key)] = str(value)
    return out


def header_get(headers: dict[str, str], name: str) -> str:
    want = name.lower()
    for key, value in headers.items():
        if key.lower() == want:
            return value
    return ""


async def default_ws_connect(url: str):
    import inspect
    import websockets

    kwargs: dict = {}
    params = inspect.signature(websockets.connect).parameters
    if "proxy" in params:
        kwargs["proxy"] = None
    return await websockets.connect(url, **kwargs)
