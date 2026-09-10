from datetime import datetime, timezone

from app.engine.schedule_timing import (
    next_run_at,
    normalize_timing,
    summarize_timing,
)
from app.time import DISPLAY_TZ


def test_normalize_interval_from_hours():
    spec = normalize_timing(None, interval_hours=6)
    assert spec == {"kind": "interval", "interval_hours": 6.0}


def test_normalize_daily_defaults():
    spec = normalize_timing({"kind": "daily"})
    assert spec["hour"] == 9
    assert spec["minute"] == 0


def test_daily_next_is_tomorrow_if_todays_slot_passed():
    now = datetime(2026, 9, 10, 10, 0, tzinfo=DISPLAY_TZ)
    nxt = next_run_at({"kind": "daily", "hour": 9, "minute": 0}, now=now)
    local = nxt.astimezone(DISPLAY_TZ)
    assert local.day == 11
    assert local.hour == 9
    assert local.minute == 0


def test_weekdays_skip_weekend():
    # 2026-09-11 周五 10:00 → 下周一 09:00
    now = datetime(2026, 9, 11, 10, 0, tzinfo=DISPLAY_TZ)
    nxt = next_run_at(
        {"kind": "weekdays", "hour": 9, "minute": 0, "weekdays": [0, 1, 2, 3, 4]},
        now=now,
    )
    local = nxt.astimezone(DISPLAY_TZ)
    assert local.weekday() == 0
    assert local.day == 14
    assert local.hour == 9


def test_weekly_monday():
    now = datetime(2026, 9, 10, 8, 0, tzinfo=DISPLAY_TZ)  # 周四
    nxt = next_run_at(
        {"kind": "weekly", "hour": 9, "minute": 0, "weekdays": [0]},
        now=now,
    )
    local = nxt.astimezone(DISPLAY_TZ)
    assert local.weekday() == 0
    assert local.day == 14


def test_monthly_rolls_to_next_month():
    now = datetime(2026, 9, 10, 10, 0, tzinfo=DISPLAY_TZ)
    nxt = next_run_at(
        {"kind": "monthly", "day_of_month": 10, "hour": 9, "minute": 0},
        now=now,
    )
    local = nxt.astimezone(DISPLAY_TZ)
    assert (local.month, local.day, local.hour) == (10, 10, 9)


def test_hourly_next_minute():
    now = datetime(2026, 9, 10, 10, 20, tzinfo=DISPLAY_TZ)
    nxt = next_run_at({"kind": "hourly", "minute": 0}, now=now)
    local = nxt.astimezone(DISPLAY_TZ)
    assert local.hour == 11
    assert local.minute == 0


def test_cron_weekdays_nine():
    now = datetime(2026, 9, 10, 10, 0, tzinfo=DISPLAY_TZ)
    nxt = next_run_at({"kind": "cron", "cron": "0 9 * * 1-5"}, now=now)
    local = nxt.astimezone(DISPLAY_TZ)
    assert local.weekday() == 4  # 周五
    assert local.hour == 9


def test_interval_from_utc():
    now = datetime(2026, 9, 10, 2, 0, tzinfo=timezone.utc)
    nxt = next_run_at({"kind": "interval", "interval_hours": 2}, now=now)
    assert nxt == datetime(2026, 9, 10, 4, 0, tzinfo=timezone.utc)


def test_summarize_daily():
    text = summarize_timing({"kind": "daily", "hour": 9, "minute": 30})
    assert "每天 09:30" in text
    assert "北京时间" in text
