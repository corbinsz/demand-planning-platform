import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.models import InventorySnapshot, Order, OrderLineItem, Product

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
    last_updated: str


async def get_latest_snapshots(
    session: AsyncSession, source: str
) -> dict[str, dict]:
    """Get the most recent snapshot per SKU for a given source."""
    subq = (
        select(
            InventorySnapshot.sku,
            func.max(InventorySnapshot.recorded_at).label("max_recorded"),
        )
        .where(InventorySnapshot.source == source)
        .group_by(InventorySnapshot.sku)
        .subquery()
    )

    result = await session.execute(
        select(InventorySnapshot)
        .join(
            subq,
            and_(
                InventorySnapshot.sku == subq.c.sku,
                InventorySnapshot.recorded_at == subq.c.max_recorded,
                InventorySnapshot.source == source,
            ),
        )
    )
    snapshots = result.scalars().all()
    return {s.sku: _snapshot_to_dict(s) for s in snapshots}


def _snapshot_to_dict(s: InventorySnapshot) -> dict:
    return {
        "sku": s.sku,
        "quantity_on_hand": s.quantity_on_hand,
        "quantity_allocated": s.quantity_allocated,
        "quantity_available": s.quantity_available,
        "warehouse": s.warehouse or "",
        "recorded_at": s.recorded_at,
    }


async def calculate_daily_velocity(session: AsyncSession, sku: str, days: int = 30) -> float:
    """Calculate average daily sales velocity from order line items."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await session.execute(
        select(func.coalesce(func.sum(OrderLineItem.quantity), 0))
        .join(Order, OrderLineItem.order_id == Order.order_id)
        .where(
            OrderLineItem.sku == sku,
            Order.created_at >= cutoff,
        )
    )
    total_sold = result.scalar_one()
    return round(total_sold / max(days, 1), 2)


async def _get_all_daily_velocities(session: AsyncSession, days: int = 30) -> dict[str, float]:
    """Batch query: average daily sales velocity for ALL SKUs in one query."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
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
    """
    Join Shopify and ShipHero inventory by SKU.
    ShipHero = source of truth for on-hand quantities.
    Shopify = source of truth for sales velocity.
    """
    async with async_session() as session:
        shiphero_data = await get_latest_snapshots(session, "shiphero")
        shopify_data = await get_latest_snapshots(session, "shopify")

        products_result = await session.execute(select(Product))
        products = {p.sku: p.title for p in products_result.scalars().all()}

        all_skus = set(shiphero_data.keys()) | set(shopify_data.keys())
        records = []

        velocity_map = await _get_all_daily_velocities(session)

        def _safe_dt(d):
            """Normalize datetime to naive UTC for safe comparison."""
            if d is None:
                return datetime.min
            if hasattr(d, 'tzinfo') and d.tzinfo is not None:
                return d.astimezone(timezone.utc).replace(tzinfo=None)
            return d

        for sku in sorted(all_skus):
            sh = shiphero_data.get(sku)
            sp = shopify_data.get(sku)

            on_hand = sh["quantity_on_hand"] if sh else 0
            allocated = sh["quantity_allocated"] if sh else 0
            available = sh["quantity_available"] if sh else 0
            warehouse = sh["warehouse"] if sh else ""

            shopify_available = sp["quantity_available"] if sp else None
            discrepancy = (shopify_available - on_hand) if shopify_available is not None else 0

            velocity = velocity_map.get(sku, 0.0)
            days_of_stock = round(available / velocity, 1) if velocity > 0 else None

            sh_dt = _safe_dt(sh["recorded_at"] if sh else None)
            sp_dt = _safe_dt(sp["recorded_at"] if sp else None)
            last_updated = max(sh_dt, sp_dt)

            records.append(
                UnifiedInventoryRecord(
                    sku=sku,
                    title=products.get(sku, "Unknown"),
                    quantity_on_hand=on_hand,
                    quantity_allocated=allocated,
                    quantity_available=available,
                    shopify_available=shopify_available,
                    discrepancy=discrepancy,
                    has_discrepancy=abs(discrepancy) > 0,
                    warehouse=warehouse,
                    daily_velocity=velocity,
                    days_of_stock=days_of_stock,
                    last_updated=last_updated.isoformat() if last_updated != datetime.min else None,
                )
            )

    logger.info(
        f"Reconciled {len(records)} SKUs, "
        f"{sum(1 for r in records if r.has_discrepancy)} with discrepancies"
    )
    return records


async def get_discrepancies() -> list[UnifiedInventoryRecord]:
    """Return only SKUs with inventory discrepancies between sources."""
    records = await reconcile_inventory()
    return [r for r in records if r.has_discrepancy]
