"""Small datetime helpers.

SQLite often hands back naive timestamps. PostgreSQL may hand back aware
ones. Comparisons and "is this promo active?" need one clock.
"""

from datetime import UTC, datetime


def as_utc(value: datetime) -> datetime:
    """Return ``value`` as an aware UTC datetime.

    Naive values are treated as UTC, which is how this app writes them.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def as_date_str(value: object) -> str | None:
    """Calendar day ``YYYY-MM-DD`` from a date, datetime, or string."""
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())[:10]
    return str(value)[:10]


def is_active_window(
    start: datetime,
    end: datetime,
    now: datetime | None = None,
) -> bool:
    """True when ``now`` falls inside ``[start, end]``."""
    current = now or datetime.now(UTC)
    return as_utc(start) <= current <= as_utc(end)
