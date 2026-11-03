"""Small SQL helpers that work on both SQLite and Postgres."""

from sqlalchemy import func


def day_key(column):
    """Bucket a timestamp to a YYYY-MM-DD string on SQLite and Postgres."""
    return func.date(column)


def like_contains(term: str) -> str:
    """Escape LIKE wildcards so a search is a literal substring."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
