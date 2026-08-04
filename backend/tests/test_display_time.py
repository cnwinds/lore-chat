from app.time import DISPLAY_TZ, now_display, now_iso_seconds


def test_now_iso_seconds_has_china_offset():
    ts = now_iso_seconds()
    assert ts.endswith("+08:00") or "+08:00" in ts


def test_now_display_tz():
    assert now_display().tzinfo == DISPLAY_TZ
