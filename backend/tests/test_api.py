"""Integration coverage: tenancy, today screen, share links, deletion, promotions."""

from datetime import timedelta

from sqlalchemy import select

from app.database import async_session
from app.models.models import InventorySnapshot, Order, OrderLineItem, Product, Workspace
from app.timeutil import utcnow_naive


def _auth(client, email, name):
    response = client.post("/api/auth/register", json={
        "email": email,
        "password": "a-long-password",
        "workspace_name": name,
    })
    assert response.status_code == 200, response.text
    return response.json()["token"]


def _stock(client, token, sku, title, available, days_ago_orders):
    import asyncio

    async def insert():
        async with async_session() as session:
            ws = (await session.execute(select(Workspace))).scalars().all()
            # The token's workspace is the one we just created; tests insert explicitly below.
            _ = ws

    asyncio.run(insert())
    # Insert through the session using the workspace id from /api/auth/me
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    workspace_id = me["workspace"]["id"]

    async def write():
        async with async_session() as session:
            session.add(Product(workspace_id=workspace_id, sku=sku, title=title, cost_price=10))
            now = utcnow_naive()
            for offset in range(days_ago_orders, 0, -1):
                if offset % 2:
                    continue
                order_id = f"{workspace_id}-{sku}-{offset}"
                when = now - timedelta(days=offset)
                session.add(Order(
                    workspace_id=workspace_id,
                    order_id=order_id,
                    created_at=when,
                    total_price=20,
                ))
                session.add(OrderLineItem(
                    workspace_id=workspace_id,
                    line_item_id=order_id + "-li",
                    order_id=order_id,
                    sku=sku,
                    quantity=2,
                    price=20,
                ))
            session.add(InventorySnapshot(
                workspace_id=workspace_id,
                snapshot_id=f"{workspace_id}-{sku}-slc",
                sku=sku,
                quantity_on_hand=available + 1,
                quantity_allocated=1,
                quantity_available=available,
                warehouse="Salt Lake City, UT",
                source="shiphero",
                recorded_at=now,
            ))
            session.add(InventorySnapshot(
                workspace_id=workspace_id,
                snapshot_id=f"{workspace_id}-{sku}-vegas",
                sku=sku,
                quantity_on_hand=2,
                quantity_allocated=0,
                quantity_available=2,
                warehouse="Las Vegas, NV",
                source="shiphero",
                recorded_at=now,
            ))
            await session.commit()

    import asyncio
    asyncio.run(write())


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["database"] == "ok"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_tenant_isolation_and_today(client):
    token_a = _auth(client, "a@example.com", "Brand A")
    token_b = _auth(client, "b@example.com", "Brand B")
    _stock(client, token_a, "TEE-1", "Tee", available=4, days_ago_orders=40)
    _stock(client, token_b, "HAT-9", "Hat", available=50, days_ago_orders=20)

    headers_a = {"Authorization": f"Bearer {token_a}"}
    inventory = client.get("/api/inventory", headers=headers_a)
    assert inventory.status_code == 200
    skus = {item["sku"] for item in inventory.json()["items"]}
    assert "TEE-1" in skus
    assert "HAT-9" not in skus
    # Two warehouses are both current. Available sums to 6, not a historical double count.
    detail = client.get("/api/inventory/sku/TEE-1", headers=headers_a)
    assert detail.status_code == 200
    assert detail.json()["current_stock"]["available"] == 6

    today = client.get("/api/today", headers=headers_a)
    assert today.status_code == 200
    body = today.json()
    assert "lead" in body
    assert isinstance(body["alerts"], list)

    missing = client.get("/api/today")
    assert missing.status_code == 401


def test_share_link_is_read_only_and_pdf(client):
    token = _auth(client, "c@example.com", "Brand C")
    _stock(client, token, "SOCK-1", "Socks", available=3, days_ago_orders=30)
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post("/api/reports/share", headers=headers)
    assert created.status_code == 200, created.text
    url_token = created.json()["token"]
    shared = client.get(f"/api/reports/share/{url_token}")
    assert shared.status_code == 200
    assert shared.json()["shared"] is True
    pdf = client.get("/api/reports/brief.pdf", headers=headers)
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
    digest = client.get("/api/digest", headers=headers)
    assert digest.status_code == 200
    assert "Mountain Time (Utah)" in digest.json()["schedule"]
    assert "Order these first" in digest.json()["text"]


def test_promo_validation_and_deletion(client):
    token = _auth(client, "d@example.com", "Brand D")
    headers = {"Authorization": f"Bearer {token}"}
    bad = client.post("/api/promotions", headers=headers, json={
        "name": "Too soon",
        "start_date": "2026-05-10T00:00:00",
        "end_date": "2026-05-01T00:00:00",
        "discount_pct": 10,
    })
    assert bad.status_code == 422
    good = client.post("/api/promotions", headers=headers, json={
        "name": "Spring",
        "start_date": "2026-05-01T00:00:00",
        "end_date": "2026-05-10T00:00:00",
        "discount_pct": 15,
    })
    assert good.status_code == 200
    listed = client.get("/api/promotions", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    denied = client.request("DELETE", "/api/account/data", headers=headers, json={"confirm": "wrong"})
    assert denied.status_code == 422
    wiped = client.request("DELETE", "/api/account/data", headers=headers, json={"confirm": "d@example.com"})
    assert wiped.status_code == 200
    after = client.get("/api/promotions", headers=headers)
    assert after.json()["total"] == 0


def test_sync_without_connection_is_a_sentence(client):
    token = _auth(client, "e@example.com", "Brand E")
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post("/api/sync/trigger/shopify", headers=headers)
    assert response.status_code == 200
    assert response.json()["started"] is False
    assert "not connected" in response.json()["message"].lower()


def test_one_brand_cannot_read_or_edit_another(client):
    token_a = _auth(client, "iso-a@example.com", "Iso A")
    token_b = _auth(client, "iso-b@example.com", "Iso B")
    _stock(client, token_a, "SKU-A", "Alpha tee", available=6, days_ago_orders=30)
    _stock(client, token_b, "SKU-B", "Beta hat", available=8, days_ago_orders=30)
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    assert client.get("/api/inventory/sku/SKU-B", headers=headers_a).status_code == 404
    assert client.get("/api/inventory/sku/SKU-A", headers=headers_b).status_code == 404

    rule = {
        "reorder_point": 12,
        "reorder_quantity": 24,
        "lead_time_days": 10,
        "safety_stock": 3,
    }
    assert client.put("/api/purchase-orders/rules/SKU-B", headers=headers_a, json=rule).status_code == 404
    assert client.put("/api/purchase-orders/rules/SKU-A", headers=headers_a, json=rule).status_code == 200
    other_rules = client.get("/api/purchase-orders/rules", headers=headers_b).json()["items"]
    assert [row["sku"] for row in other_rules] == []

    created = client.post("/api/promotions", headers=headers_a, json={
        "name": "A only",
        "start_date": "2026-06-01T00:00:00",
        "end_date": "2026-06-08T00:00:00",
        "discount_pct": 10,
    })
    assert created.status_code == 200
    promo_id = created.json()["id"]
    assert client.get("/api/promotions", headers=headers_b).json()["total"] == 0
    assert client.delete(f"/api/promotions/{promo_id}", headers=headers_b).status_code == 404
    assert client.get("/api/promotions", headers=headers_a).json()["total"] == 1

    shared = client.post("/api/reports/share", headers=headers_a)
    assert shared.status_code == 200
    brief = client.get(f"/api/reports/share/{shared.json()['token']}").json()
    titles = " ".join(row.get("title", "") for row in brief.get("stockout_risks", []) + brief.get("reorders", []) + brief.get("dead_stock", []))
    assert "Beta hat" not in titles
    assert "Alpha" in brief["workspace_name"] or brief["workspace_name"] == "Iso A"

    wiped = client.request("DELETE", "/api/account/data", headers=headers_a, json={"confirm": "iso-a@example.com"})
    assert wiped.status_code == 200
    assert client.get("/api/inventory/sku/SKU-A", headers=headers_a).status_code == 404
    assert client.get("/api/inventory/sku/SKU-B", headers=headers_b).status_code == 200

    audits = client.get("/api/audit", headers=headers_b).json()["items"]
    assert all("iso-a" not in (row.get("actor") or "") for row in audits)


def test_reorder_rule_round_trip_keeps_safety_stock(client):
    token = _auth(client, "safety@example.com", "Safety Co")
    _stock(client, token, "SAFE-1", "Safe sock", available=1, days_ago_orders=20)
    headers = {"Authorization": f"Bearer {token}"}
    saved = client.put("/api/purchase-orders/rules/SAFE-1", headers=headers, json={
        "reorder_point": 15,
        "reorder_quantity": 40,
        "lead_time_days": 21,
        "safety_stock": 9,
    })
    assert saved.status_code == 200
    assert saved.json()["safety_stock"] == 9
    listed = client.get("/api/purchase-orders/rules", headers=headers).json()["items"]
    assert listed[0]["safety_stock"] == 9
    assert listed[0]["lead_time_days"] == 21


def test_client_error_hook_accepts_a_short_message(client):
    response = client.post("/api/client-errors", json={"message": "boom", "path": "/today"})
    assert response.status_code == 200
    assert response.json()["ok"] is True
