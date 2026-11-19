"""Async SQLAlchemy engine, sessions, and schema bootstrap.

The app creates tables on startup. Alembic is in the repo for later
migrations; the running containers do not depend on a revision history.
"""

import os
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import func
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import Settings, get_settings

_BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
_DEFAULT_SQLITE_PATH = os.path.join(_BACKEND_DIR, "inventory.db")


def resolve_database_url(settings: Settings) -> str:
    """Choose the async SQLAlchemy URL.

    An explicit ``sqlite`` URL is used as given, which is how tests point at
    a temporary file. Otherwise ``USE_SQLITE=true`` (the local default) uses
    a file next to the backend package. ``USE_SQLITE=false`` uses
    ``DATABASE_URL``, which Docker Compose sets to PostgreSQL.
    """
    url = settings.database_url.strip()
    if url.startswith("sqlite"):
        return url
    if settings.use_sqlite:
        return f"sqlite+aiosqlite:///{_DEFAULT_SQLITE_PATH}"
    return url


def day_bucket(column):
    """SQL calendar day of a timestamp.

    ``date()`` exists on SQLite and PostgreSQL. ``strftime`` does not, so
    forecasts and the sales chart used to fail as soon as Postgres was the
    database.
    """
    return func.date(column)


settings = get_settings()
DATABASE_URL = resolve_database_url(settings)
_is_sqlite = DATABASE_URL.startswith("sqlite")

_engine_kwargs: dict = {"echo": False}
if _is_sqlite:
    # NullPool closes connections after each use so tests can reset the file
    # and so a sync seed script is not blocked by a checked-out connection.
    _engine_kwargs["poolclass"] = NullPool
    _engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}

engine: AsyncEngine = create_async_engine(DATABASE_URL, **_engine_kwargs)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def get_upsert() -> Any:
    """Dialect-specific INSERT ... ON CONFLICT helper."""
    if _is_sqlite:
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        return sqlite_insert
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    return pg_insert


class Base(DeclarativeBase):
    """Declarative base for every table."""


async def init_db() -> None:
    """Create any missing tables and add columns introduced by the models."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)


def _add_missing_columns(conn) -> None:
    """``ALTER TABLE ADD COLUMN`` for model fields a dev database does not have yet.

    This keeps a local SQLite file usable while the models change. It is not
    a substitute for a reviewed migration on a database you care about.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(conn)
    for table_name, table in Base.metadata.tables.items():
        if not inspector.has_table(table_name):
            continue
        existing = {column["name"] for column in inspector.get_columns(table_name)}
        for col in table.columns:
            if col.name not in existing:
                col_type = col.type.compile(conn.dialect)
                conn.execute(
                    text(f"ALTER TABLE {table_name} ADD COLUMN {col.name} {col_type}")
                )


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that commits on success and rolls back on error."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
