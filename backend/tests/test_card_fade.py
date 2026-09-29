from datetime import datetime, timedelta, timezone

from app.engine.memory.card_fade import card_fade_target


def _fact(*, status="confirmed", origin="direct", days_ago=0):
    now = datetime.now(timezone.utc)
    ts = (now - timedelta(days=days_ago)).isoformat()
    return {
        "status": status,
        "origin": origin,
        "last_seen_at": ts,
        "updated_at": ts,
    }


def test_confirmed_fades_to_stale():
    now = datetime.now(timezone.utc)
    assert card_fade_target(_fact(days_ago=181), now=now) == "stale"


def test_candidate_fades_to_rejected():
    now = datetime.now(timezone.utc)
    assert (
        card_fade_target(_fact(status="candidate", days_ago=181), now=now)
        == "rejected"
    )


def test_manual_exempt():
    now = datetime.now(timezone.utc)
    assert (
        card_fade_target(_fact(origin="manual", days_ago=400), now=now) is None
    )


def test_recent_unchanged():
    now = datetime.now(timezone.utc)
    assert card_fade_target(_fact(days_ago=30), now=now) is None
