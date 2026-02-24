import os
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

settings = get_settings()

# Use SQLite for local dev — set USE_SQLITE=true in .env to force SQLite
_db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "inventory.db")
DATABASE_URL = settings.database_url
if settings.use_sqlite or "sqlite" in DATABASE_URL:
    DATABASE_URL = f"sqlite+aiosqlite:///{_db_path}"

_is_sqlite = "sqlite" in DATABASE_URL

_engine_kwargs = {"echo": False}
if _is_sqlite:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_async_engine(DATABASE_URL, **_engine_kwargs)


def get_upsert():
    """Return the dialect-appropriate insert function for upserts."""
    if _is_sqlite:
        from sqlalchemy.dialects.sqlite import insert
    else:
        from sqlalchemy.dialects.postgresql import insert
    return insert

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    """Create all tables and add any missing columns for existing DBs."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)


def _add_missing_columns(conn):
    """ALTER TABLE ADD COLUMN for any columns defined in models but missing from DB."""
    from sqlalchemy import inspect, text
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


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
