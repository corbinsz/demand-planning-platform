"""Timezone-naive UTC helpers.

SQLite and Postgres both behave if we store UTC without a timezone flag
and compare it to UTC values that are also naive. Mixing aware and naive
datetimes raises TypeError in Python and is dialect-dependent in SQL.
"""

from datetime import datetime, timezone

from sqlalchemy.types import DateTime, TypeDecorator


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class UTCDateTime(TypeDecorator):
    """Store datetimes as naive UTC. Accept aware values on the way in."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None or not isinstance(value, datetime):
            return value
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if isinstance(value, datetime) and value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
