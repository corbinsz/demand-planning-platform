import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

import httpx
from sqlalchemy import select

from app.config import get_settings
from app.database import async_session, get_upsert
from app.models.models import Product, Order, OrderLineItem, InventorySnapshot

upsert = get_upsert()

logger = logging.getLogger(__name__)
settings = get_settings()

BASE_URL = f"https://{settings.shopify_store_domain}/admin/api/2024-01"
HEADERS = {
    "X-Shopify-Access-Token": settings.shopify_access_token,
    "Content-Type": "application/json",
}
PAGE_LIMIT = 250
MAX_RETRIES = 5


def _parse_link_header(header: str | None) -> str | None:
    """Extract next page URL from Shopify's Link header."""
    if not header:
        return None
    for part in header.split(","):
        match = re.search(r'<([^>]+)>;\s*rel="next"', part)
        if match:
            return match.group(1)
    return None


async def _request_with_backoff(
    client: httpx.AsyncClient, method: str, url: str, **kwargs
) -> httpx.Response:
    """Make HTTP request with exponential backoff for rate limiting."""
    for attempt in range(MAX_RETRIES):
        response = await client.request(method, url, **kwargs)
        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", 2 ** attempt))
            logger.warning(f"Rate limited. Retrying after {retry_after}s (attempt {attempt + 1})")
            await asyncio.sleep(retry_after)
            continue
        response.raise_for_status()
        return response
    raise httpx.HTTPStatusError(
        "Max retries exceeded", request=response.request, response=response
    )


async def fetch_all_products() -> list[dict]:
    """Fetch all products and variants with SKUs from Shopify."""
    products = []
    url = f"{BASE_URL}/products.json?limit={PAGE_LIMIT}"

    async with httpx.AsyncClient(headers=HEADERS, timeout=30) as client:
        while url:
            resp = await _request_with_backoff(client, "GET", url)
            data = resp.json()
            products.extend(data.get("products", []))
            url = _parse_link_header(resp.headers.get("Link"))
            # Respect Shopify's call limit bucket
            call_limit = resp.headers.get("X-Shopify-Shop-Api-Call-Limit", "0/40")
            used, total = map(int, call_limit.split("/"))
            if used >= total - 2:
                await asyncio.sleep(1)

    logger.info(f"Fetched {len(products)} products from Shopify")
    return products


async def fetch_orders(days: int = 365) -> list[dict]:
    """Fetch orders from the last N days with line items."""
    orders = []
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    url = (
        f"{BASE_URL}/orders.json?limit={PAGE_LIMIT}&status=any"
        f"&created_at_min={since}&fields=id,name,created_at,total_price,line_items"
    )

    async with httpx.AsyncClient(headers=HEADERS, timeout=30) as client:
        while url:
            resp = await _request_with_backoff(client, "GET", url)
            data = resp.json()
            orders.extend(data.get("orders", []))
            url = _parse_link_header(resp.headers.get("Link"))
            call_limit = resp.headers.get("X-Shopify-Shop-Api-Call-Limit", "0/40")
            used, total = map(int, call_limit.split("/"))
            if used >= total - 2:
                await asyncio.sleep(1)

    logger.info(f"Fetched {len(orders)} orders from Shopify")
    return orders


async def fetch_inventory_levels() -> list[dict]:
    """Fetch current inventory levels per location."""
    # First get locations
    locations = []
    async with httpx.AsyncClient(headers=HEADERS, timeout=30) as client:
        resp = await _request_with_backoff(client, "GET", f"{BASE_URL}/locations.json")
        locations = resp.json().get("locations", [])

        levels = []
        for loc in locations:
            url = (
                f"{BASE_URL}/inventory_levels.json"
                f"?location_ids={loc['id']}&limit={PAGE_LIMIT}"
            )
            while url:
                resp = await _request_with_backoff(client, "GET", url)
                data = resp.json()
                for level in data.get("inventory_levels", []):
                    level["location_name"] = loc.get("name", "Unknown")
                levels.extend(data.get("inventory_levels", []))
                url = _parse_link_header(resp.headers.get("Link"))

    logger.info(f"Fetched {len(levels)} inventory levels from Shopify")
    return levels


async def sync_products() -> int:
    """Sync all Shopify products into the database."""
    shopify_products = await fetch_all_products()
    count = 0

    async with async_session() as session:
        for product in shopify_products:
            for variant in product.get("variants", []):
                sku = variant.get("sku")
                if not sku:
                    continue
                stmt = (
                    upsert(Product)
                    .values(
                        sku=sku,
                        title=product.get("title", ""),
                        variant_id=str(variant.get("id", "")),
                        shopify_id=str(product.get("id", "")),
                    )
                    .on_conflict_do_update(
                        index_elements=["sku"],
                        set_={
                            "title": product.get("title", ""),
                            "variant_id": str(variant.get("id", "")),
                            "shopify_id": str(product.get("id", "")),
                        },
                    )
                )
                await session.execute(stmt)
                count += 1
        await session.commit()

    logger.info(f"Synced {count} product variants from Shopify")
    return count


async def sync_orders(days: int = 365) -> int:
    """Sync Shopify orders and line items into the database."""
    shopify_orders = await fetch_orders(days)
    count = 0

    def _parse_dt(val):
        if not val:
            return None
        if isinstance(val, datetime):
            return val
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None

    def _parse_price(val):
        if val is None:
            return None
        try:
            return Decimal(str(val))
        except (InvalidOperation, ValueError):
            return None

    async with async_session() as session:
        for order in shopify_orders:
            order_id = str(order["id"])
            created = _parse_dt(order.get("created_at"))
            total = _parse_price(order.get("total_price"))
            stmt = (
                upsert(Order)
                .values(
                    order_id=order_id,
                    shopify_order_id=order_id,
                    created_at=created,
                    total_price=total,
                )
                .on_conflict_do_update(
                    index_elements=["order_id"],
                    set_={"total_price": total},
                )
            )
            await session.execute(stmt)

            for item in order.get("line_items", []):
                sku = item.get("sku")
                if not sku:
                    continue
                li_id = str(item["id"])
                item_price = _parse_price(item.get("price"))
                stmt = (
                    upsert(OrderLineItem)
                    .values(
                        line_item_id=li_id,
                        order_id=order_id,
                        sku=sku,
                        quantity=int(item.get("quantity", 0)),
                        price=item_price,
                    )
                    .on_conflict_do_update(
                        index_elements=["line_item_id"],
                        set_={
                            "quantity": int(item.get("quantity", 0)),
                            "price": item_price,
                        },
                    )
                )
                await session.execute(stmt)
                count += 1
        await session.commit()

    logger.info(f"Synced {len(shopify_orders)} orders, {count} line items from Shopify")
    return count


async def _build_inventory_item_sku_map() -> dict[str, str]:
    """Build a mapping from Shopify inventory_item_id to product SKU."""
    products = await fetch_all_products()
    mapping = {}
    for product in products:
        for variant in product.get("variants", []):
            sku = variant.get("sku")
            inv_item_id = variant.get("inventory_item_id")
            if sku and inv_item_id:
                mapping[str(inv_item_id)] = sku
    logger.info(f"Built inventory_item_id → SKU map with {len(mapping)} entries")
    return mapping


async def sync_inventory_levels() -> int:
    """Sync Shopify inventory levels as snapshots."""
    # Build inventory_item_id → SKU map from product variants
    inv_to_sku = await _build_inventory_item_sku_map()
    levels = await fetch_inventory_levels()
    count = 0
    skipped = 0

    async with async_session() as session:
        for level in levels:
            inv_item_id = str(level.get("inventory_item_id", ""))
            sku = inv_to_sku.get(inv_item_id)
            if not sku:
                skipped += 1
                continue
            snapshot_id = f"shopify-{inv_item_id}-{level['location_id']}"
            qty = int(level.get("available") or 0)
            stmt = (
                upsert(InventorySnapshot)
                .values(
                    snapshot_id=snapshot_id,
                    sku=sku,
                    quantity_on_hand=qty,
                    quantity_allocated=0,
                    quantity_available=qty,
                    warehouse=level.get("location_name", "Unknown"),
                    source="shopify",
                )
                .on_conflict_do_update(
                    index_elements=["snapshot_id"],
                    set_={
                        "quantity_on_hand": qty,
                        "quantity_available": qty,
                    },
                )
            )
            await session.execute(stmt)
            count += 1
        await session.commit()

    if skipped:
        logger.warning(f"Skipped {skipped} inventory levels with no SKU mapping")
    logger.info(f"Synced {count} inventory level snapshots from Shopify")
    return count


async def full_sync() -> dict:
    """Run full Shopify sync: products, orders, inventory."""
    products = await sync_products()
    orders = await sync_orders()
    inventory = await sync_inventory_levels()
    return {
        "products_synced": products,
        "order_line_items_synced": orders,
        "inventory_levels_synced": inventory,
    }
