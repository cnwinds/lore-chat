from __future__ import annotations

from datetime import datetime, timedelta, timezone

CARD_FADE_DAYS = 180
CARD_CANDIDATE_DAYS = 180


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def card_fade_target(
    fact: dict,
    *,
    now: datetime,
    fade_days: int = CARD_FADE_DAYS,
    candidate_days: int = CARD_CANDIDATE_DAYS,
) -> str | None:
    if (fact.get("origin") or "") == "manual":
        return None
    base = _parse_ts(fact.get("last_seen_at")) or _parse_ts(fact.get("updated_at"))
    if base is None:
        return None
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    age = now - base
    status = fact.get("status") or ""
    if status == "candidate" and age >= timedelta(days=candidate_days):
        return "rejected"
    if status == "confirmed" and age >= timedelta(days=fade_days):
        return "stale"
    return None
