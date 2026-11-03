"""Compare Shopify available units with ShipHero available units.

Both sides are the latest snapshot per warehouse, summed. Comparing
Shopify available to ShipHero on-hand (the old behavior) flagged healthy
SKUs because those two numbers mean different things.
"""

import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.models import Order, OrderLineItem, Product
from app.services.stock import summed_stock
from app.timeutil import utcnow_naive

logger = logging.getLogger(__name__)


@dataclass
class UnifiedInventoryRecord:
    sku: str
    title: str
    quantity_on_hand: int
    quantity_allocated: int
    quantity_available: int
    shopify_available: int | None
    discrepancy: int
    has_discrepancy: bool
    warehouse: str
    daily_velocity: float
    days_of_stock: float | None
    last_updated: str | None


async def _velocities(session: AsyncSession, workspace_id: int, days: int = 30) -> dict[str, float]:
    cutoff = utcnow_naive() - timedelta(days=days)
    result = await session.execute(
        select(OrderLineItem.sku, func.coalesce(func.sum(OrderLineItem.quantity), 0))
        .join(Order, (Order.workspace_id == OrderLineItem.workspace_id) & (Order.order_id == OrderLineItem.order_id))
        .where(OrderLineItem.workspace_id == workspace_id, Order.created_at >= cutoff)
        .group_by(OrderLineItem.sku)
    )
    return {row[0]: round(int(row[1]) / max(days, 1), 2) for row in result.all()}


async def reconcile_inventory(workspace_id: int) -> list[UnifiedInventoryRecord]:
    async with async_session() as session:
        shiphero = await summed_stock(session, workspace_id, "shiphero")
        shopify = await summed_stock(session, workspace_id, "shopify")
        products = await session.execute(
            select(Product.sku, Product.title).where(Product.workspace_id == workspace_id)
        )
        titles = {sku: title for sku, title in products.all()}
        velocities = await _velocities(session, workspace_id)

    records = []
    for sku in sorted(set(shiphero) | set(shopify)):
        sh = shiphero.get(sku)
        sp = shopify.get(sku)
        available = int(sh["available"]) if sh else 0
        on_hand = int(sh["on_hand"]) if sh else 0
        allocated = int(sh["allocated"]) if sh else 0
        shopify_available = int(sp["available"]) if sp else None
        discrepancy = (shopify_available - available) if shopify_available is not None else 0
        velocity = velocities.get(sku, 0.0)
        warehouses = (sh or sp or {}).get("warehouses") or []
        recorded = None
        for side in (sh, sp):
            if side and side.get("recorded_at") and (recorded is None or side["recorded_at"] > recorded):
                recorded = side["recorded_at"]
        records.append(UnifiedInventoryRecord(
            sku=sku,
            title=titles.get(sku, "Unknown"),
            quantity_on_hand=on_hand,
            quantity_allocated=allocated,
            quantity_available=available,
            shopify_available=shopify_available,
            discrepancy=discrepancy,
            has_discrepancy=shopify_available is not None and abs(discrepancy) > 0,
            warehouse=", ".join(warehouses),
            daily_velocity=velocity,
            days_of_stock=round(available / velocity, 1) if velocity > 0 else None,
            last_updated=recorded.isoformat() if recorded else None,
        ))
    logger.info(
        "Reconciled workspace %s: %s SKUs, %s discrepancies",
        workspace_id,
        len(records),
        sum(1 for r in records if r.has_discrepancy),
    )
    return records


async def get_discrepancies(workspace_id: int) -> list[UnifiedInventoryRecord]:
    records = await reconcile_inventory(workspace_id)
    return [r for r in records if r.has_discrepancy]
