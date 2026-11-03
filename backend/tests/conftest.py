import os
import tempfile
from pathlib import Path

_dir = tempfile.mkdtemp(prefix="ii-test-")
_db = str(Path(_dir) / "test.db")
os.environ["USE_SQLITE"] = "true"
os.environ["SQLITE_PATH"] = _db
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_db}"
os.environ["DATABASE_URL_SYNC"] = f"sqlite:///{_db}"
os.environ["DEMO_MODE"] = "false"
os.environ["AUTO_SEED"] = "false"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["WARM_FORECASTS"] = "false"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production-use"
os.environ["ALLOW_ENV_CREDENTIALS"] = "false"
os.environ["SHOPIFY_ACCESS_TOKEN"] = ""
os.environ["SHIPHERO_API_TOKEN"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    import asyncio

    async def reset():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(reset())
    with TestClient(app) as test_client:
        yield test_client
