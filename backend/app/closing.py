from __future__ import annotations

from typing import Any


def close_quietly(obj: Any) -> None:
    closer = getattr(obj, "close", None)
    if not callable(closer):
        return
    try:
        closer()
    except Exception:
        pass
