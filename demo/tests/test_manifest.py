import json
from datetime import date
from pathlib import Path

MANIFEST = Path(__file__).resolve().parents[1] / "manifest.json"


def test_manifest_exists_and_parses():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert data["format_version"] == 1


def test_reference_date_is_iso():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    date.fromisoformat(data["reference_date"])


def test_manifest_declares_required_keys():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for key in ("format_version", "reference_date", "content_version", "persona"):
        assert key in data
