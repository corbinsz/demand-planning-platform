"""Shared API client. The database is a temporary SQLite file."""

import sqlite3

import pytest

import tests.support  # noqa: F401  -- must run before the app is imported
from tests.support import DB_PATH


@pytest.fixture(scope="session")
def client():
    """One app process for the suite. The scheduler stays off."""
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _clean_database(client):
    """Each test starts from an empty catalog and an empty forecast cache."""
    from app.services.backtest import clear_backtest_cache
    from app.services.forecasting import clear_forecast_cache

    connection = sqlite3.connect(DB_PATH)
    connection.execute("PRAGMA foreign_keys = OFF")
    tables = (
        "order_line_items",
        "orders",
        "inventory_snapshots",
        "reorder_rules",
        "promotional_periods",
        "products",
        "job_logs",
    )
    for table in tables:
        connection.execute(f"DELETE FROM {table}")
    connection.commit()
    connection.close()
    clear_forecast_cache()
    clear_backtest_cache()
    yield
