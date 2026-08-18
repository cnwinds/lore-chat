import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.timeshift import compute_offset_days, shift_in_place, shift_iso_timestamp


def test_compute_offset_days():
    assert compute_offset_days("2026-08-18", date(2026, 9, 17)) == 30
    assert compute_offset_days("2026-08-18", date(2026, 8, 18)) == 0


def test_shift_iso_timestamp_keeps_time_of_day():
    out = shift_iso_timestamp("2026-08-18T09:30:00+00:00", 30)
    assert out.startswith("2026-09-17T09:30:00")


def test_shift_iso_timestamp_handles_zulu():
    assert shift_iso_timestamp("2026-08-18T09:30:00Z", 1).startswith("2026-08-19T09:30:00")


def test_shift_iso_timestamp_passes_through_garbage():
    assert shift_iso_timestamp("not-a-date", 30) == "not-a-date"
    assert shift_iso_timestamp("", 30) == ""


def test_shift_in_place_walks_nested_structures():
    payload = {
        "created_at": "2026-08-18T00:00:00+00:00",
        "title": "不该动",
        "messages": [{"ts": "2026-08-18T01:00:00+00:00", "text": "也不该动"}],
    }
    out = shift_in_place(payload, 1, {"created_at", "ts"})
    assert out["created_at"].startswith("2026-08-19")
    assert out["messages"][0]["ts"].startswith("2026-08-19")
    assert out["title"] == "不该动"
    assert out["messages"][0]["text"] == "也不该动"


def test_zero_offset_is_identity():
    payload = {"ts": "2026-08-18T00:00:00+00:00"}
    assert shift_in_place(payload, 0, {"ts"})["ts"] == "2026-08-18T00:00:00+00:00"
