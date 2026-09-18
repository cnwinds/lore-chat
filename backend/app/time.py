"""产品内面向用户的时间：统一中国标准时间（Asia/Shanghai）。"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

DISPLAY_TZ = ZoneInfo("Asia/Shanghai")
DISPLAY_TZ_LABEL = "北京时间"


def now_display() -> datetime:
    return datetime.now(timezone.utc).astimezone(DISPLAY_TZ)


def now_iso_seconds() -> str:
    """带 +08:00 偏移的 ISO8601，供 SSE、会话库等机器解析。"""
    return now_display().isoformat(timespec="seconds")


def now_epoch_ms() -> int:
    """UTC 纪元毫秒，供秒表锚点；与浏览器 Date.now() 同一量纲。"""
    return int(now_display().timestamp() * 1000)


def now_wall_clock() -> str:
    """`YYYY-MM-DD HH:mm:ss`，供文档 frontmatter、changelog 等直接展示。"""
    return now_display().strftime("%Y-%m-%d %H:%M:%S")


def parse_search_instant(raw: str | None) -> datetime | None:
    """解析检索用时刻；日期视为当天 00:00 北京时间；无时区则按北京时间。"""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        try:
            return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=DISPLAY_TZ)
        except ValueError:
            return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=DISPLAY_TZ)
    return dt.astimezone(DISPLAY_TZ)


def normalize_search_ts(raw: str | None) -> str | None:
    """会话检索时间下界/上界：写成带 +08:00 的 ISO；无法解析则原样保留。"""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    instant = parse_search_instant(s)
    if instant is None:
        return s
    return instant.isoformat(timespec="seconds")


def ts_in_search_range(ts: str, after: str | None, before: str | None) -> bool:
    stamp_dt = parse_search_instant(ts)
    after_dt = parse_search_instant(after) if after else None
    before_dt = parse_search_instant(before) if before else None
    if stamp_dt is not None and (after_dt is not None or before_dt is not None):
        if after_dt is not None and stamp_dt < after_dt:
            return False
        if before_dt is not None and stamp_dt >= before_dt:
            return False
        return True
    stamp = ts or ""
    if after and stamp < after:
        return False
    if before and stamp >= before:
        return False
    return True

