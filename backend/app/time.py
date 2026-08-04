"""产品内面向用户的时间：统一中国标准时间（Asia/Shanghai）。"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

DISPLAY_TZ = ZoneInfo("Asia/Shanghai")
DISPLAY_TZ_LABEL = "北京时间"


def now_display() -> datetime:
    return datetime.now(timezone.utc).astimezone(DISPLAY_TZ)


def now_iso_seconds() -> str:
    """带 +08:00 偏移的 ISO8601，供 SSE、会话库与文档元数据使用。"""
    return now_display().isoformat(timespec="seconds")
