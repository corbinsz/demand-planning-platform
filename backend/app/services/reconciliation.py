"""Compare Shopify and ShipHero stock for the same SKU.

ShipHero is the warehouse system, so its available units are the planning
number. A discrepancy is the difference in available units, not a mix of
Shopify available and ShipHero on-hand (those are different measures and
almost always disagree).
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.models import Order, OrderLineItem, Product
from app.services.stock import StockPosition, positions_by_sku
from app.timeutil import as_utc

logger = logging.getLogger(__name__)


@dataclass
class UnifiedInventoryRecord:
    """One SKU joined across the store and the warehouse."""

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


def _recorded(position: StockPosition | None) -> datetime:
    if position is None or position.recorded_at is None:
        return datetime.min.replace(tzinfo=UTC)
    return as_utc(position.recorded_at)


async def _velocities(session: AsyncSession, days: int = 30) -> dict[str, float]:
    """Average daily units sold per SKU over ``days``."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    result = await session.execute(
        select(
            OrderLineItem.sku,
            func.coalesce(func.sum(OrderLineItem.quantity), 0).label("total_sold"),
        )
        .join(Order, OrderLineItem.order_id == Order.order_id)
        .where(Order.created_at >= cutoff)
        .group_by(OrderLineItem.sku)
    )
    return {row[0]: round(int(row[1]) / max(days, 1), 2) for row in result.all()}


async def reconcile_inventory() -> list[UnifiedInventoryRecord]:
    """Join the latest Shopify and ShipHero positions by SKU."""
    async with async_session() as session:
        shiphero = await positions_by_sku(session, "shiphero")
        shopify = await positions_by_sku(session, "shopify")
        products_result = await session.execute(select(Product.sku, Product.title))
        titles = {sku: title for sku, title in products_result.all()}
        velocity_map = await _velocities(session)

    records: list[UnifiedInventoryRecord] = []
    for sku in sorted(set(shiphero) | set(shopify)):
        warehouse_pos = shiphero.get(sku)
        store_pos = shopify.get(sku)
        available = warehouse_pos.available if warehouse_pos else 0
        shopify_available = store_pos.available if store_pos else None
        discrepancy = (
            (shopify_available - available) if shopify_available is not None else 0
        )
        velocity = velocity_map.get(sku, 0.0)
        last_updated = max(_recorded(warehouse_pos), _recorded(store_pos))
        records.append(
            UnifiedInventoryRecord(
                sku=sku,
                title=titles.get(sku, "Unknown"),
                quantity_on_hand=warehouse_pos.on_hand if warehouse_pos else 0,
                quantity_allocated=warehouse_pos.allocated if warehouse_pos else 0,
                quantity_available=available,
                shopify_available=shopify_available,
                discrepancy=discrepancy,
                has_discrepancy=shopify_available is not None and discrepancy != 0,
                warehouse=warehouse_pos.warehouses if warehouse_pos else "",
                daily_velocity=velocity,
                days_of_stock=round(available / velocity, 1) if velocity > 0 else None,
                last_updated=last_updated.isoformat(),
            )
        )

    mismatched = sum(1 for record in records if record.has_discrepancy)
    logger.info("Reconciled %s SKUs, %s with discrepancies", len(records), mismatched)
    return records


async def get_discrepancies() -> list[UnifiedInventoryRecord]:
    """SKUs whose Shopify and ShipHero available units do not match."""
    records = await reconcile_inventory()
    return [record for record in records if record.has_discrepancy]
