"""Synthetic catalog shape, and sync clients that must not hit the network."""

import asyncio

from app.services.shiphero_sync import (
    fetch_open_purchase_orders,
)
from app.services.shiphero_sync import (
    full_sync as shiphero_full_sync,
)
from app.services.shopify_sync import _parse_link_header, _request_with_backoff
from app.services.shopify_sync import full_sync as shopify_full_sync
from seed import SKU_PREFIX, _build_catalog


def test_demo_catalog_is_the_invented_brand():
    products = _build_catalog()
    assert len(products) >= 50
    titles = " ".join(product["title"] for product in products)
    assert "Veldt Trail Shoe" in titles
    assert "Ember Day Tee" in titles
    assert "Enamel Camp Cup" in titles
    assert all(product["sku"].startswith(SKU_PREFIX) for product in products)
    assert "2.0" not in titles


def test_shopify_link_header_returns_the_next_url_only():
    header = '<https://example.test/products?page=2>; rel="next", <https://example.test/products?page=1>; rel="previous"'
    assert _parse_link_header(header) == "https://example.test/products?page=2"
    assert _parse_link_header(None) is None
    assert _parse_link_header('rel="previous"') is None


def test_shopify_retries_a_429_then_returns_the_next_response():
    calls = {"count": 0}

    def handler(request):
        calls["count"] += 1
        if calls["count"] == 1:
            return __import__("httpx").Response(429, headers={"Retry-After": "0"})
        return __import__("httpx").Response(200, json={"ok": True})

    async def _run():
        import httpx

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http:
            response = await _request_with_backoff(
                http, "GET", "https://example.test/products"
            )
            return response.status_code

    assert asyncio.run(_run()) == 200
    assert calls["count"] == 2


def test_sync_with_placeholder_tokens_does_not_leave_the_process():
    assert asyncio.run(shopify_full_sync())["products_synced"] == 0
    assert asyncio.run(shiphero_full_sync())["inventory_synced"] == 0
    assert asyncio.run(fetch_open_purchase_orders()) == []
