"""角色例行任务的定时规格：日历时刻（北京时间）或间隔。

kind:
  interval  — 每隔 N 小时（兼容旧字段 interval_hours）
  hourly    — 每小时的第 M 分
  daily     — 每天 HH:MM
  weekdays  — 每个工作日（周一至周五）HH:MM
  weekly    — 每周指定星期 HH:MM（weekdays: 0=周一 … 6=周日）
  monthly   — 每月指定日 HH:MM
  cron      — 五段 cron（分 时 日 月 周；周 0/7=周日），按北京时间
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.time import DISPLAY_TZ, DISPLAY_TZ_LABEL

SCHEDULE_KINDS = (
    "interval",
    "hourly",
    "daily",
    "weekdays",
    "weekly",
    "monthly",
    "cron",
)

_WEEKDAY_NAMES = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
_WORKDAYS = (0, 1, 2, 3, 4)


def _as_int(value: Any, *, lo: int, hi: int, field: str) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"{field} 无效") from e
    if n < lo or n > hi:
        raise ValueError(f"{field} 须在 {lo}–{hi}")
    return n


def _hhmm(hour: int, minute: int) -> str:
    return f"{hour:02d}:{minute:02d}"


def _local(now: datetime | None = None) -> datetime:
    dt = now or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(DISPLAY_TZ)


def _to_utc_iso(local_dt: datetime) -> str:
    return local_dt.astimezone(timezone.utc).isoformat()


def normalize_timing(raw: dict[str, Any] | None, *, interval_hours: float | None = None) -> dict[str, Any]:
    """把 API / 工具参数规范成可持久化的 timing。"""
    data = dict(raw or {})
    kind = str(data.get("kind") or "").strip()
    if not kind:
        if interval_hours is not None:
            kind = "interval"
            data["interval_hours"] = interval_hours
        else:
            raise ValueError("请提供 timing.kind 或 interval_hours")
    if kind not in SCHEDULE_KINDS:
        raise ValueError(
            "timing.kind 须为 interval/hourly/daily/weekdays/weekly/monthly/cron"
        )

    minute = data.get("minute")
    hour = data.get("hour")
    if kind == "interval":
        hours = data.get("interval_hours", interval_hours)
        if hours is None:
            raise ValueError("间隔定时须提供 interval_hours")
        try:
            hours_f = float(hours)
        except (TypeError, ValueError) as e:
            raise ValueError("interval_hours 无效") from e
        if hours_f < 0.5:
            raise ValueError("间隔至少 0.5 小时")
        return {"kind": "interval", "interval_hours": hours_f}

    if kind == "hourly":
        m = 0 if minute is None else _as_int(minute, lo=0, hi=59, field="minute")
        return {"kind": "hourly", "minute": m}

    if kind == "cron":
        cron = str(data.get("cron") or "").strip()
        if not cron:
            raise ValueError("高级定时须提供 cron 表达式")
        _validate_cron(cron)
        return {"kind": "cron", "cron": cron}

    h = 9 if hour is None else _as_int(hour, lo=0, hi=23, field="hour")
    m = 0 if minute is None else _as_int(minute, lo=0, hi=59, field="minute")

    if kind == "daily":
        return {"kind": "daily", "hour": h, "minute": m}

    if kind == "weekdays":
        return {"kind": "weekdays", "hour": h, "minute": m, "weekdays": list(_WORKDAYS)}

    if kind == "weekly":
        days = data.get("weekdays")
        if not days:
            days = [0]
        parsed: list[int] = []
        for d in days:
            parsed.append(_as_int(d, lo=0, hi=6, field="weekdays"))
        uniq = sorted(set(parsed))
        if not uniq:
            raise ValueError("每周定时至少选择一天")
        return {"kind": "weekly", "hour": h, "minute": m, "weekdays": uniq}

    if kind == "monthly":
        day = data.get("day_of_month", 1)
        dom = _as_int(day, lo=1, hi=31, field="day_of_month")
        return {"kind": "monthly", "hour": h, "minute": m, "day_of_month": dom}

    raise ValueError(f"未知 timing.kind: {kind}")


def timing_from_row(row) -> dict[str, Any]:
    """从 sqlite 行恢复 timing；旧行仅有 interval_hours。"""
    kind = None
    spec: dict[str, Any] = {}
    try:
        kind = row["kind"]
    except (KeyError, IndexError):
        kind = None
    try:
        raw = row["spec_json"]
    except (KeyError, IndexError):
        raw = None
    if raw:
        import json

        try:
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                spec = loaded
        except (TypeError, ValueError):
            spec = {}
    hours = None
    try:
        hours = float(row["interval_hours"])
    except (KeyError, IndexError, TypeError, ValueError):
        hours = None
    if kind:
        spec.setdefault("kind", kind)
    if hours is not None and spec.get("kind") == "interval":
        spec.setdefault("interval_hours", hours)
    if not spec.get("kind"):
        return normalize_timing(None, interval_hours=hours if hours is not None else 24)
    return normalize_timing(spec, interval_hours=hours)


def interval_hours_for_storage(timing: dict[str, Any]) -> float:
    """保留 interval_hours 列：间隔种用真值，日历种用 24 占位。"""
    if timing.get("kind") == "interval":
        return float(timing["interval_hours"])
    return 24.0


def summarize_timing(timing: dict[str, Any]) -> str:
    kind = timing.get("kind")
    tz = DISPLAY_TZ_LABEL
    if kind == "interval":
        hours = timing.get("interval_hours")
        return f"每 {hours:g} 小时"
    if kind == "hourly":
        return f"每小时第 {int(timing.get('minute', 0))} 分（{tz}）"
    if kind == "daily":
        return f"每天 {_hhmm(int(timing['hour']), int(timing['minute']))}（{tz}）"
    if kind == "weekdays":
        return f"每个工作日 {_hhmm(int(timing['hour']), int(timing['minute']))}（{tz}）"
    if kind == "weekly":
        days = timing.get("weekdays") or [0]
        names = "、".join(_WEEKDAY_NAMES[int(d)] for d in days)
        return f"每{names} {_hhmm(int(timing['hour']), int(timing['minute']))}（{tz}）"
    if kind == "monthly":
        return (
            f"每月 {int(timing.get('day_of_month', 1))} 日 "
            f"{_hhmm(int(timing['hour']), int(timing['minute']))}（{tz}）"
        )
    if kind == "cron":
        return f"cron `{timing.get('cron')}`（{tz}）"
    return "定时"


def next_run_at(timing: dict[str, Any], *, now: datetime | None = None) -> datetime:
    """下次触发时刻（aware UTC）。"""
    kind = timing["kind"]
    utc_now = now or datetime.now(timezone.utc)
    if utc_now.tzinfo is None:
        utc_now = utc_now.replace(tzinfo=timezone.utc)
    if kind == "interval":
        return utc_now + timedelta(hours=float(timing["interval_hours"]))
    local = utc_now.astimezone(DISPLAY_TZ)
    if kind == "hourly":
        return _next_hourly(local, int(timing.get("minute", 0))).astimezone(timezone.utc)
    if kind == "daily":
        return _next_on_weekdays(
            local, int(timing["hour"]), int(timing["minute"]), set(range(7))
        ).astimezone(timezone.utc)
    if kind == "weekdays":
        return _next_on_weekdays(
            local, int(timing["hour"]), int(timing["minute"]), set(_WORKDAYS)
        ).astimezone(timezone.utc)
    if kind == "weekly":
        days = {int(d) for d in (timing.get("weekdays") or [0])}
        return _next_on_weekdays(
            local, int(timing["hour"]), int(timing["minute"]), days
        ).astimezone(timezone.utc)
    if kind == "monthly":
        return _next_monthly(
            local,
            int(timing.get("day_of_month", 1)),
            int(timing["hour"]),
            int(timing["minute"]),
        ).astimezone(timezone.utc)
    if kind == "cron":
        return _next_cron(local, str(timing["cron"])).astimezone(timezone.utc)
    raise ValueError(f"未知 timing.kind: {kind}")


def next_run_iso(timing: dict[str, Any], *, now: datetime | None = None) -> str:
    return next_run_at(timing, now=now).isoformat()


def _at(local: datetime, hour: int, minute: int) -> datetime:
    return local.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _next_hourly(local: datetime, minute: int) -> datetime:
    cand = local.replace(minute=minute, second=0, microsecond=0)
    if cand <= local:
        cand += timedelta(hours=1)
    return cand


def _next_on_weekdays(
    local: datetime, hour: int, minute: int, allowed: set[int]
) -> datetime:
    if not allowed:
        raise ValueError("未指定星期")
    for offset in range(0, 8):
        day = local + timedelta(days=offset)
        cand = _at(day, hour, minute)
        if cand.weekday() in allowed and cand > local:
            return cand
    raise ValueError("无法计算下次运行时间")


def _next_monthly(local: datetime, day: int, hour: int, minute: int) -> datetime:
    year, month = local.year, local.month
    for _ in range(48):
        try:
            cand = local.replace(
                year=year, month=month, day=day, hour=hour, minute=minute,
                second=0, microsecond=0,
            )
        except ValueError:
            cand = None
        if cand is not None and cand > local:
            return cand
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
    raise ValueError("无法计算下次运行时间")


def _cron_unrestricted(field: str) -> bool:
    return field.strip() == "*"


def _cron_values(field: str, lo: int, hi: int) -> frozenset[int]:
    field = field.strip()
    if not field:
        raise ValueError("cron 字段为空")
    out: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        step = 1
        if "/" in part:
            base, step_s = part.split("/", 1)
            try:
                step = int(step_s)
            except ValueError as e:
                raise ValueError(f"cron 步长无效: {part}") from e
            if step <= 0:
                raise ValueError("cron 步长须为正整数")
            part = base.strip() or "*"
        if part == "*":
            start, end = lo, hi
        elif "-" in part:
            a, b = part.split("-", 1)
            try:
                start, end = int(a), int(b)
            except ValueError as e:
                raise ValueError(f"cron 范围无效: {part}") from e
        else:
            try:
                n = int(part)
            except ValueError as e:
                raise ValueError(f"cron 字段无效: {part}") from e
            if step == 1:
                if lo <= n <= hi:
                    out.add(n)
                continue
            start, end = n, hi
        if start > end:
            raise ValueError(f"cron 范围起止颠倒: {part}")
        for v in range(start, end + 1, step):
            if lo <= v <= hi:
                out.add(v)
    if not out:
        raise ValueError(f"cron 字段无有效取值: {field}")
    return frozenset(out)


def _validate_cron(expr: str) -> None:
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError("cron 须为 5 段：分 时 日 月 周")
    _cron_values(parts[0], 0, 59)
    _cron_values(parts[1], 0, 23)
    _cron_values(parts[2], 1, 31)
    _cron_values(parts[3], 1, 12)
    _cron_values(parts[4], 0, 7)


def _next_in(values: frozenset[int], current: int) -> int | None:
    greater = [v for v in values if v >= current]
    return min(greater) if greater else None


def _cron_day_ok(
    t: datetime,
    doms: frozenset[int],
    dows: frozenset[int],
    dom_star: bool,
    dow_star: bool,
) -> bool:
    cron_dow = t.isoweekday() % 7  # Sun=0 … Sat=6
    dom_ok = t.day in doms
    dow_ok = cron_dow in dows
    if not dom_star and not dow_star:
        return dom_ok or dow_ok
    return (dom_star or dom_ok) and (dow_star or dow_ok)


def _next_cron(local: datetime, expr: str) -> datetime:
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError("cron 须为 5 段：分 时 日 月 周")
    minutes = _cron_values(parts[0], 0, 59)
    hours = _cron_values(parts[1], 0, 23)
    doms = _cron_values(parts[2], 1, 31)
    months = _cron_values(parts[3], 1, 12)
    dows = set(_cron_values(parts[4], 0, 7))
    if 7 in dows:
        dows.add(0)
        dows.discard(7)
    dows_f = frozenset(dows)
    dom_star = _cron_unrestricted(parts[2])
    dow_star = _cron_unrestricted(parts[4])

    t = local.replace(second=0, microsecond=0) + timedelta(minutes=1)
    deadline = t + timedelta(days=400)
    while t < deadline:
        if t.month not in months:
            year = t.year + (1 if t.month == 12 else 0)
            month = 1 if t.month == 12 else t.month + 1
            t = t.replace(year=year, month=month, day=1, hour=0, minute=0)
            continue
        if t.hour not in hours:
            nxt = _next_in(hours, t.hour + 1)
            if nxt is None:
                t = (t.replace(hour=0, minute=0) + timedelta(days=1))
            else:
                t = t.replace(hour=nxt, minute=min(minutes))
            continue
        if t.minute not in minutes:
            nxt = _next_in(minutes, t.minute)
            if nxt is None:
                t = t.replace(minute=0) + timedelta(hours=1)
            else:
                t = t.replace(minute=nxt)
            continue
        if _cron_day_ok(t, doms, dows_f, dom_star, dow_star):
            return t
        t = t.replace(minute=0) + timedelta(hours=1)
    raise ValueError("无法计算下次运行时间")
