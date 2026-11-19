"""HTTP coverage for the planning endpoints."""

from datetime import UTC, datetime, timedelta

from app.database import day_bucket
from app.models.models import Order
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from tests.factories import add_order, add_product, add_rule, add_snapshot


def test_day_bucket_does_not_use_sqlite_strftime_on_postgres():
    statement = select(day_bucket(Order.created_at))
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "strftime" not in sql.lower()
    assert "date(" in sql.lower()


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_empty_dashboard_is_zero(client):
    body = client.get("/api/dashboard").json()
    assert body["total_skus"] == 0
    assert body["total_on_hand_units"] == 0
    assert body["orders_last_30d"] == 0
    assert body["skus_below_reorder"] == 0
    assert body["revenue_at_risk_daily"] == 0


def test_sales_trend_counts_each_order_total_once(client):
    add_product("VE-A", "Alpha")
    yesterday = datetime.now(UTC) - timedelta(days=1)
    add_order(
        [("VE-A", 1, "30.00"), ("VE-A", 1, "50.00")],
        total="80.00",
        when=yesterday,
    )
    items = client.get("/api/dashboard/sales-trend?days=7").json()["items"]
    assert len(items) == 1
    assert items[0]["orders"] == 1
    assert items[0]["units"] == 2
    assert items[0]["revenue"] == 80.0


def test_stock_sums_latest_snapshot_per_warehouse_and_ignores_history(client):
    add_product("VE-SH-FG-9", "Veldt Trail Shoe", cost="46.00")
    old = datetime.now(UTC) - timedelta(days=3)
    recent = datetime.now(UTC) - timedelta(hours=1)
    add_snapshot(
        "VE-SH-FG-9",
        source="shiphero",
        warehouse="Demo North Warehouse",
        on_hand=500,
        available=500,
        when=old,
    )
    add_snapshot(
        "VE-SH-FG-9",
        source="shiphero",
        warehouse="Demo North Warehouse",
        on_hand=10,
        available=10,
        when=recent,
    )
    add_snapshot(
        "VE-SH-FG-9",
        source="shiphero",
        warehouse="Demo South Warehouse",
        on_hand=4,
        available=4,
        when=recent,
    )
    add_rule("VE-SH-FG-9", reorder_point=14, reorder_quantity=12, lead_time_days=14)
    when = datetime.now(UTC) - timedelta(days=2)
    add_order([("VE-SH-FG-9", 1, "128.00")], total="128.00", when=when)

    dashboard = client.get("/api/dashboard").json()
    assert dashboard["total_on_hand_units"] == 14
    assert dashboard["skus_below_reorder"] == 1
    assert dashboard["total_inventory_cost"] == round(14 * 46, 2)

    detail = client.get("/api/inventory/sku/VE-SH-FG-9").json()
    assert detail["current_stock"]["available"] == 14
    assert "Demo North Warehouse" in detail["current_stock"]["warehouse"]
    assert "Demo South Warehouse" in detail["current_stock"]["warehouse"]


def test_reconciliation_compares_available_units(client):
    add_product("VE-MATCH", "Matched")
    add_product("VE-DIFF", "Different")
    # On-hand differs, available matches: not a discrepancy.
    add_snapshot(
        "VE-MATCH",
        source="shiphero",
        warehouse="Demo North Warehouse",
        on_hand=15,
        available=10,
        allocated=5,
    )
    add_snapshot(
        "VE-MATCH",
        source="shopify",
        warehouse="Demo North Warehouse",
        on_hand=10,
        available=10,
        allocated=0,
    )
    add_snapshot(
        "VE-DIFF",
        source="shiphero",
        warehouse="Demo North Warehouse",
        on_hand=10,
        available=10,
    )
    add_snapshot(
        "VE-DIFF",
        source="shopify",
        warehouse="Demo North Warehouse",
        on_hand=8,
        available=8,
    )

    rows = {
        row["sku"]: row
        for row in client.get("/api/inventory/reconciled").json()["items"]
    }
    assert rows["VE-MATCH"]["has_discrepancy"] is False
    assert rows["VE-MATCH"]["discrepancy"] == 0
    assert rows["VE-DIFF"]["has_discrepancy"] is True
    assert rows["VE-DIFF"]["discrepancy"] == -2

    flagged = client.get("/api/inventory/discrepancies").json()["items"]
    assert [row["sku"] for row in flagged] == ["VE-DIFF"]


def test_missing_sku_is_404_and_inventory_search_finds_a_title(client):
    add_product("VE-CUP-TN", "Enamel Camp Cup 12oz - Tin")
    add_snapshot(
        "VE-CUP-TN", source="shiphero", warehouse="Demo North Warehouse", on_hand=3
    )
    assert client.get("/api/inventory/sku/VE-NOPE").status_code == 404
    found = client.get("/api/inventory", params={"search": "Camp Cup"}).json()
    assert found["total"] == 1
    assert found["items"][0]["sku"] == "VE-CUP-TN"
    warehouses = client.get("/api/inventory/warehouses").json()["warehouses"]
    assert warehouses == ["Demo North Warehouse"]


def test_forecast_and_purchase_suggestion_for_a_short_history(client):
    add_product("VE-TEE-PB-M", "Ember Day Tee - Pebble / M")
    add_snapshot(
        "VE-TEE-PB-M",
        source="shiphero",
        warehouse="Demo North Warehouse",
        on_hand=2,
        available=2,
    )
    start = datetime.now(UTC) - timedelta(days=6)
    for offset in range(5):
        add_order(
            [("VE-TEE-PB-M", 2, "42.00")],
            total="84.00",
            when=start + timedelta(days=offset),
        )

    forecast = client.get("/api/forecasting/VE-TEE-PB-M").json()
    assert forecast["forecast_30d"] == 60
    assert forecast["forecast_60d"] == 120
    assert forecast["forecast_90d"] == 180
    assert forecast["current_stock"] == 2
    assert forecast["below_reorder_point"] is True

    suggestions = client.get("/api/purchase-orders/suggestions").json()["items"]
    assert len(suggestions) == 1
    assert suggestions[0]["sku"] == "VE-TEE-PB-M"
    assert suggestions[0]["urgency"] == "critical"
    assert suggestions[0]["suggested_quantity"] > 0

    alerts = client.get("/api/forecasting/alerts").json()
    assert alerts["total"] == 1
    assert alerts["items"][0]["urgency"] == "critical"
    assert client.get("/api/dashboard").json()["skus_below_reorder"] == alerts["total"]


def test_abc_dead_stock_and_excess_reports(client):
    add_product("VE-A", "Class A")
    add_product("VE-B", "Class B")
    add_product("VE-C", "Class C")
    add_product("VE-DEAD", "Never sold")
    add_product("VE-HEAP", "Too many")
    when = datetime.now(UTC) - timedelta(days=3)
    add_order([("VE-A", 1, "85.00")], total="85.00", when=when)
    add_order([("VE-B", 1, "10.00")], total="10.00", when=when)
    add_order([("VE-C", 1, "5.00")], total="5.00", when=when)
    add_order(
        [("VE-HEAP", 10, "24.00")],
        total="240.00",
        when=datetime.now(UTC) - timedelta(days=40),
    )
    for sku, available in (
        ("VE-A", 5),
        ("VE-B", 5),
        ("VE-C", 5),
        ("VE-DEAD", 12),
        ("VE-HEAP", 400),
    ):
        add_snapshot(
            sku, source="shiphero", warehouse="Demo North Warehouse", on_hand=available
        )

    classes = {
        item["sku"]: item["abc_class"]
        for item in client.get("/api/analytics/abc?days=30&per_page=20").json()["items"]
    }
    assert classes["VE-A"] == "A"
    assert classes["VE-B"] == "B"
    assert classes["VE-C"] == "C"

    dead = client.get("/api/analytics/dead-stock").json()
    dead_skus = {item["sku"] for item in dead["items"]}
    assert "VE-DEAD" in dead_skus
    never = next(item for item in dead["items"] if item["sku"] == "VE-DEAD")
    assert never["days_since_last_sale"] is None
    assert never["recommendation"] == "Liquidate or write off"

    excess = client.get("/api/analytics/excess-stock?target_days=30").json()
    heap = next(item for item in excess["items"] if item["sku"] == "VE-HEAP")
    assert heap["excess_units"] > 0
    assert heap["excess_value"] > 0

    exported = client.get("/api/analytics/abc/export").text
    assert exported.splitlines()[0].startswith("SKU,Title,Class")


def test_promotion_lifecycle_and_inverted_dates(client):
    now = datetime.now(UTC)
    created = client.post(
        "/api/promotions",
        json={
            "name": "Demo week",
            "start_date": (now - timedelta(days=1)).isoformat(),
            "end_date": (now + timedelta(days=2)).isoformat(),
            "discount_pct": 10,
            "notes": "Synthetic",
        },
    )
    assert created.status_code == 200
    promo_id = created.json()["id"]
    listed = client.get("/api/promotions").json()["items"]
    assert listed[0]["name"] == "Demo week"
    assert listed[0]["is_active"] is True

    rejected = client.post(
        "/api/promotions",
        json={
            "name": "Backwards",
            "start_date": (now + timedelta(days=5)).isoformat(),
            "end_date": now.isoformat(),
            "discount_pct": 0,
        },
    )
    assert rejected.status_code == 422

    updated = client.put(f"/api/promotions/{promo_id}", json={"discount_pct": 12})
    assert updated.status_code == 200
    assert client.delete(f"/api/promotions/{promo_id}").json()["deleted"] is True
    assert (
        client.put("/api/promotions/9999", json={"name": "missing"}).status_code == 404
    )


def test_reorder_rule_upsert_and_open_purchase_orders_without_a_token(client):
    created = client.put(
        "/api/purchase-orders/rules/VE-NEW",
        json={
            "reorder_point": 8,
            "reorder_quantity": 16,
            "lead_time_days": 12,
            "safety_stock": 2,
        },
    )
    assert created.status_code == 200
    rules = client.get("/api/purchase-orders/rules").json()["items"]
    assert rules[0]["sku"] == "VE-NEW"
    assert rules[0]["reorder_quantity"] == 16

    updated = client.put(
        "/api/purchase-orders/rules/VE-NEW",
        json={
            "reorder_point": 9,
            "reorder_quantity": 18,
            "lead_time_days": 12,
            "safety_stock": 2,
        },
    )
    assert updated.json()["reorder_point"] == 9

    open_orders = client.get("/api/purchase-orders").json()
    assert open_orders["items"] == []
    assert "error" not in open_orders


def test_connection_checks_do_not_call_out_with_placeholder_tokens(client):
    shopify = client.post("/api/sync/test-shopify").json()
    shiphero = client.post("/api/sync/test-shiphero").json()
    assert shopify["success"] is False
    assert shiphero["success"] is False
    assert "not set" in shopify["error"]
    assert "not set" in shiphero["error"]
    status = client.get("/api/sync/status").json()
    assert status["shopify_running"] is False
    assert status["jobs"]["shopify_full_sync"]["status"] == "never_run"
