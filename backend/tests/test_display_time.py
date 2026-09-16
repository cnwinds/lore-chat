from app.time import DISPLAY_TZ, now_display, now_epoch_ms, now_iso_seconds, now_wall_clock


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
