"""Shared window and change calculations."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def parse_date(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def in_window(item: dict, start: datetime, end: datetime) -> bool:
    posted = parse_date(item["posted_at"])
    return start <= posted < end


def growth(current: int | float, previous: int | float) -> float | None:
    if previous == 0:
        return None if current == 0 else 100.0
    return round((current - previous) / previous * 100, 1)


def windows(now: datetime, short_days: int, long_days: int) -> dict[str, tuple[datetime, datetime]]:
    return {
        "current_7d": (now - timedelta(days=short_days), now),
        "previous_7d": (now - timedelta(days=short_days * 2), now - timedelta(days=short_days)),
        "current_30d": (now - timedelta(days=long_days), now),
        "previous_30d": (now - timedelta(days=long_days * 2), now - timedelta(days=long_days)),
    }

