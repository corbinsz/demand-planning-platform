import os
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import event, inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

_default_sqlite = os.path.join(os.path.dirname(os.path.dirname(__file__)), "inventory.db")


def _resolve_async_url() -> str:
    if settings.use_sqlite or settings.database_url.startswith("sqlite"):
        path = settings.sqlite_path or _default_sqlite
        return f"sqlite+aiosqlite:///{path}"
    return settings.database_url


DATABASE_URL = _resolve_async_url()
_is_sqlite = DATABASE_URL.startswith("sqlite")

_engine_kwargs: dict = {"echo": False}
if _is_sqlite:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_async_engine(DATABASE_URL, **_engine_kwargs)


@event.listens_for(engine.sync_engine, "connect")
def _enable_sqlite_fk(dbapi_conn, connection_record):
    if engine.dialect.name == "sqlite":
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_upsert() -> Any:
    """Return the dialect-appropriate insert function for upserts."""
    import importlib
    module = "sqlalchemy.dialects.sqlite" if _is_sqlite else "sqlalchemy.dialects.postgresql"
    return importlib.import_module(module).insert


async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    """Create all tables and add any missing columns for existing DBs."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)


def _add_missing_columns(conn):
    """ALTER TABLE ADD COLUMN for columns added after a database was created.

    This does not rewrite unique constraints. If you are upgrading an older
    file, delete it and reseed — see docs/TESTING.md.
    """
    inspector = inspect(conn)
    for table_name, table in Base.metadata.tables.items():
        if not inspector.has_table(table_name):
            continue
        existing = {c["name"] for c in inspector.get_columns(table_name)}
        for col in table.columns:
            if col.name not in existing:
                col_type = col.type.compile(conn.dialect)
                conn.execute(text(
                    f'ALTER TABLE {table_name} ADD COLUMN {col.name} {col_type}'
                ))


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
