"""在导入 Chroma / FTS 之前将过旧的系统 sqlite3 替换为 pysqlite3。"""

from __future__ import annotations

import sys


def ensure_modern_sqlite() -> None:
    try:
        import sqlite3 as _stdlib

        if tuple(int(x) for x in _stdlib.sqlite_version.split(".")[:2]) >= (3, 35):
            return
    except Exception:
        pass
    try:
        import pysqlite3  # type: ignore

        sys.modules["sqlite3"] = pysqlite3
    except ImportError:
        pass


ensure_modern_sqlite()
