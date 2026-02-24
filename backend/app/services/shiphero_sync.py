import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from app.config import get_settings
from app.database import async_session, get_upsert
from app.models.models import InventorySnapshot

upsert = get_upsert()

logger = logging.getLogger(__name__)
settings = get_settings()

GRAPHQL_URL = "https://public-api.shiphero.com/graphql"
HEADERS = {
    "Authorization": f"Bearer {settings.shiphero_api_token}",
    "Content-Type": "application/json",
}
TIMEOUT = 60
MAX_RETRIES = 5
BASE_BACKOFF = 1.0  # seconds


async def _graphql_request(
    query: str, variables: dict | None = None, client: httpx.AsyncClient | None = None
) -> dict:
    """Execute a GraphQL request against ShipHero API with retry + exponential backoff."""
    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    async def _do(c: httpx.AsyncClient):
        for attempt in range(MAX_RETRIES):
            try:
                resp = await c.post(GRAPHQL_URL, headers=HEADERS, json=payload)

                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after else BASE_BACKOFF * (2 ** attempt)
                    logger.warning(f"ShipHero 429 rate limited, retrying in {wait:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})")
                    await asyncio.sleep(wait)
                    continue

                if resp.status_code >= 500 and attempt < MAX_RETRIES - 1:
                    wait = BASE_BACKOFF * (2 ** attempt)
                    logger.warning(f"ShipHero {resp.status_code} server error, retrying in {wait:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})")
                    await asyncio.sleep(wait)
                    continue

                resp.raise_for_status()
                data = resp.json()

                # ShipHero returns throttle info in the response body
                complexity = data.get("data", {})
                for key in complexity:
                    if isinstance(complexity[key], dict) and "complexity" in complexity[key]:
                        remaining = complexity[key].get("complexity")
                        if remaining is not None and isinstance(remaining, (int, float)) and remaining < 100:
                            logger.info(f"ShipHero API complexity low ({remaining}), adding 1s delay")
                            await asyncio.sleep(1.0)
                        break

                if "errors" in data:
                    error_msg = data["errors"][0].get("message", "Unknown error")
                    # Retry on throttle errors embedded in GraphQL response
                    if "throttle" in error_msg.lower() or "rate" in error_msg.lower():
                        wait = BASE_BACKOFF * (2 ** attempt)
                        logger.warning(f"ShipHero GraphQL throttle error, retrying in {wait:.1f}s: {error_msg}")
                        await asyncio.sleep(wait)
                        continue
                    logger.error(f"ShipHero GraphQL errors: {data['errors']}")
                    raise RuntimeError(f"ShipHero API error: {error_msg}")

                return data.get("data", {})

            except httpx.TimeoutException:
                if attempt < MAX_RETRIES - 1:
                    wait = BASE_BACKOFF * (2 ** attempt)
                    logger.warning(f"ShipHero request timeout, retrying in {wait:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})")
                    await asyncio.sleep(wait)
                    continue
                raise

        # Exhausted all retries
        raise RuntimeError(f"ShipHero API request failed after {MAX_RETRIES} retries")

    if client:
        return await _do(client)
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        return await _do(c)


INVENTORY_QUERY = """
query($after: String) {
  inventory {
    request_id
    complexity
    data(first: 100, after: $after) {
      pageInfo {
        hasNextPage
        endCursor
      }
      edges {
        node {
          sku
          warehouse_products {
            warehouse_id
            warehouse_identifier
            on_hand
            inventory_bin {
              zone
            }
            allocated
            available
            backorder
          }
        }
      }
    }
  }
}
"""

PURCHASE_ORDERS_QUERY = """
query($after: String) {
  purchase_orders {
    request_id
    data(first: 50, after: $after) {
      pageInfo {
        hasNextPage
        endCursor
      }
      edges {
        node {
          id
          po_number
          vendor_id
          warehouse_id
          po_date
          date_expected
          fulfillment_status
          line_items {
            edges {
              node {
                sku
                quantity
                quantity_received
                price
              }
            }
          }
        }
      }
    }
  }
}
"""

INVENTORY_CHANGES_QUERY = """
query($date_from: ISODateTime, $date_to: ISODateTime, $after: String) {
  inventory_changes(
    date_from: $date_from
    date_to: $date_to
  ) {
    request_id
    data(first: 100, after: $after) {
      pageInfo {
        hasNextPage
        endCursor
      }
      edges {
        node {
          sku
          previous_on_hand
          change_in_on_hand
          reason
          location_name
          created_at
        }
      }
    }
  }
}
"""


def _safe_int(val, default=0):
    """Safely convert a value to int (ShipHero sometimes returns strings)."""
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


async def fetch_inventory() -> list[dict]:
    """Fetch current inventory by SKU across all warehouses."""
    all_items = []
    cursor = None

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        while True:
            variables = {"after": cursor} if cursor else {}
            data = await _graphql_request(INVENTORY_QUERY, variables, client=client)

            inventory = data.get("inventory", {}).get("data", {})
            edges = inventory.get("edges", [])

            for edge in edges:
                node = edge.get("node", {})
                sku = node.get("sku")
                if not sku:
                    continue
                for wp in node.get("warehouse_products", []):
                    all_items.append({
                        "sku": sku,
                        "warehouse_id": wp.get("warehouse_id"),
                        "warehouse": wp.get("warehouse_identifier", ""),
                        "on_hand": _safe_int(wp.get("on_hand")),
                        "allocated": _safe_int(wp.get("allocated")),
                        "available": _safe_int(wp.get("available")),
                    })

            page_info = inventory.get("pageInfo", {})
            if page_info.get("hasNextPage"):
                cursor = page_info.get("endCursor")
            else:
                break

    logger.info(f"Fetched {len(all_items)} inventory records from ShipHero")
    return all_items


async def fetch_open_purchase_orders() -> list[dict]:
    """Fetch open purchase orders with expected receipt dates."""
    all_pos = []
    cursor = None

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        while True:
            variables = {"after": cursor} if cursor else {}
            data = await _graphql_request(PURCHASE_ORDERS_QUERY, variables, client=client)

            pos = data.get("purchase_orders", {}).get("data", {})
            edges = pos.get("edges", [])

            for edge in edges:
                node = edge.get("node", {})
                if node.get("fulfillment_status") in ("closed", "cancelled"):
                    continue
                line_items = []
                for li_edge in (node.get("line_items") or {}).get("edges", []):
                    li_node = li_edge.get("node", {})
                    line_items.append({
                        "sku": li_node.get("sku"),
                        "quantity": _safe_int(li_node.get("quantity")),
                        "quantity_received": _safe_int(li_node.get("quantity_received")),
                        "price": li_node.get("price"),
                    })
                all_pos.append({
                    "id": node.get("id"),
                    "po_number": node.get("po_number"),
                    "warehouse_id": node.get("warehouse_id"),
                    "po_date": node.get("po_date"),
                    "date_expected": node.get("date_expected"),
                    "status": node.get("fulfillment_status"),
                    "line_items": line_items,
                })

            page_info = pos.get("pageInfo", {})
            if page_info.get("hasNextPage"):
                cursor = page_info.get("endCursor")
            else:
                break

    logger.info(f"Fetched {len(all_pos)} open POs from ShipHero")
    return all_pos


async def fetch_recent_adjustments(days: int = 30) -> list[dict]:
    """Fetch inventory adjustments from the last N days."""
    adjustments = []
    cursor = None
    date_from = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    date_to = datetime.now(timezone.utc).isoformat()

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        while True:
            variables = {"date_from": date_from, "date_to": date_to}
            if cursor:
                variables["after"] = cursor
            data = await _graphql_request(INVENTORY_CHANGES_QUERY, variables, client=client)

            changes = data.get("inventory_changes", {}).get("data", {})
            edges = changes.get("edges", [])

            for edge in edges:
                adjustments.append(edge.get("node", {}))

            page_info = changes.get("pageInfo", {})
            if page_info.get("hasNextPage"):
                cursor = page_info.get("endCursor")
            else:
                break

    logger.info(f"Fetched {len(adjustments)} inventory adjustments from ShipHero")
    return adjustments


async def sync_inventory() -> int:
    """Upsert ShipHero inventory into InventorySnapshot table."""
    items = await fetch_inventory()
    count = 0

    async with async_session() as session:
        for item in items:
            sku = item.get("sku")
            if not sku:
                continue
            wh_id = item.get("warehouse_id", "default")
            snapshot_id = f"shiphero-{sku}-{wh_id}"
            on_hand = _safe_int(item.get("on_hand"))
            allocated = _safe_int(item.get("allocated"))
            available = _safe_int(item.get("available"))
            stmt = (
                upsert(InventorySnapshot)
                .values(
                    snapshot_id=snapshot_id,
                    sku=sku,
                    quantity_on_hand=on_hand,
                    quantity_allocated=allocated,
                    quantity_available=available,
                    warehouse=item.get("warehouse", ""),
                    source="shiphero",
                )
                .on_conflict_do_update(
                    index_elements=["snapshot_id"],
                    set_={
                        "quantity_on_hand": on_hand,
                        "quantity_allocated": allocated,
                        "quantity_available": available,
                        "warehouse": item.get("warehouse", ""),
                    },
                )
            )
            await session.execute(stmt)
            count += 1
        await session.commit()

    logger.info(f"Synced {count} inventory snapshots from ShipHero")
    return count


async def full_sync() -> dict:
    """Run full ShipHero sync."""
    inventory_count = await sync_inventory()
    purchase_orders = await fetch_open_purchase_orders()
    adjustments = await fetch_recent_adjustments()
    return {
        "inventory_synced": inventory_count,
        "open_purchase_orders": len(purchase_orders),
        "recent_adjustments": len(adjustments),
    }
