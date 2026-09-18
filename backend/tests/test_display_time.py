from app.time import (
    DISPLAY_TZ,
    normalize_search_ts,
    now_display,
    now_epoch_ms,
    now_iso_seconds,
    now_wall_clock,
    ts_in_search_range,
)


def test_now_iso_seconds_has_china_offset():
    ts = now_iso_seconds()
    assert "+08:00" in ts


def test_now_epoch_ms_is_unix_millis():
    ms = now_epoch_ms()
    assert ms > 1_700_000_000_000
    assert abs(ms - int(now_display().timestamp() * 1000)) < 5


def test_now_display_tz():
    assert now_display().tzinfo == DISPLAY_TZ


def test_now_wall_clock_format():
    s = now_wall_clock()
    assert len(s) == 19
    assert s[4] == "-" and s[7] == "-" and s[10] == " "
    assert s[13] == ":" and s[16] == ":"


def test_normalize_search_ts_date_is_beijing_midnight():
    assert normalize_search_ts("2026-09-17") == "2026-09-17T00:00:00+08:00"
    assert normalize_search_ts("  ") is None
    zulu = normalize_search_ts("2026-09-17T16:00:00Z")
    assert zulu == "2026-09-18T00:00:00+08:00"


def test_ts_in_search_range_uses_instants():
    assert ts_in_search_range(
        "2026-09-17T15:00:00+08:00",
        "2026-09-17",
        "2026-09-18",
    )
    assert not ts_in_search_range(
        "2026-08-12T10:00:00+08:00",
        "2026-09-17",
        "2026-09-18",
    )
    assert not ts_in_search_range(
        "2026-09-18T00:00:00+08:00",
        "2026-09-17",
        "2026-09-18",
    )
