from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

STALE_DAYS_GOAL_PROJECT = 90
DECAY_DAYS_INFERRED = 180
DECAY_DAYS_CANDIDATE = 180

_PROTECTED_ORIGINS = frozenset({"manual", "explicit_remember"})
_PROTECTED_CATEGORIES = frozenset({"identity"})


@dataclass(frozen=True)
class DecayConfig:
    stale_days_goal_project: int = STALE_DAYS_GOAL_PROJECT
    decay_days_inferred: int = DECAY_DAYS_INFERRED
    decay_days_candidate: int = DECAY_DAYS_CANDIDATE


def is_decay_exempt(fact: dict) -> bool:
    if fact.get("origin") in _PROTECTED_ORIGINS:
        return True
    if fact.get("category") in _PROTECTED_CATEGORIES:
        return True
    return False


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def decay_target_status(fact: dict, *, now: datetime, config: DecayConfig) -> str | None:
    """返回新 status，None 表示不变化。"""
    if is_decay_exempt(fact):
        return None
    status = fact.get("status")
    if status in ("forgotten", "superseded", "rejected"):
        return None
    last = _parse_ts(fact.get("last_seen_at")) or _parse_ts(fact.get("updated_at"))
    if last is None:
        return None
    age = now - last
    category = fact.get("category", "preference")
    origin = fact.get("origin", "inferred")

    if status == "candidate":
        if age >= timedelta(days=config.decay_days_candidate):
            return "rejected"
        return None

    if status == "confirmed":
        if category in ("goal", "project"):
            if age >= timedelta(days=config.stale_days_goal_project):
                return "stale"
        if origin == "inferred" and category in ("preference", "workflow"):
            if age >= timedelta(days=config.decay_days_inferred):
                return "candidate"
    return None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
