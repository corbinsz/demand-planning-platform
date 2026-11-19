"""Environment for the test process. Imported before the application."""

import os
import tempfile
from pathlib import Path

ROOT = Path(tempfile.mkdtemp(prefix="demand-planning-"))
DB_PATH = ROOT / "test.db"

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB_PATH}"
os.environ["DATABASE_URL_SYNC"] = f"sqlite:///{DB_PATH}"
os.environ["USE_SQLITE"] = "false"
os.environ["DISABLE_SCHEDULER"] = "true"
os.environ["SHOPIFY_ACCESS_TOKEN"] = "replace-me"
os.environ["SHIPHERO_API_TOKEN"] = "replace-me"
os.environ["SHOPIFY_STORE_DOMAIN"] = "demo-store.example"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["SEED_ON_START"] = "false"
os.environ["LOG_LEVEL"] = "WARNING"
