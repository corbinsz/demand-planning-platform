"""Current stock from append-only inventory snapshots.

Each sync inserts a new row. The on-hand figure for a SKU is the newest
row in each warehouse, added together. Using every historical row double
counts. Using only the single newest row drops every warehouse but one.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import InventorySnapshot


@dataclass
class StockPosition:
    """Sellable stock for one SKU across warehouses."""

    sku: str
    on_hand: int
    allocated: int
    available: int
    warehouses: str
    recorded_at: datetime | None


def latest_snapshot_ids(source: str):
    """Subquery: newest snapshot id per SKU and warehouse for ``source``."""
    return (
        select(
            InventorySnapshot.sku.label("sku"),
            InventorySnapshot.warehouse.label("warehouse"),
            func.max(InventorySnapshot.id).label("max_id"),
        )
        .where(InventorySnapshot.source == source)
        .group_by(InventorySnapshot.sku, InventorySnapshot.warehouse)
        .subquery()
    )


def _combine(sku: str, snaps: list[InventorySnapshot]) -> StockPosition:
    recorded = [snap.recorded_at for snap in snaps if snap.recorded_at is not None]
    warehouses = sorted({snap.warehouse for snap in snaps if snap.warehouse})
    return StockPosition(
        sku=sku,
        on_hand=sum(int(snap.quantity_on_hand or 0) for snap in snaps),
        allocated=sum(int(snap.quantity_allocated or 0) for snap in snaps),
        available=sum(int(snap.quantity_available or 0) for snap in snaps),
        warehouses=", ".join(warehouses),
        recorded_at=max(recorded) if recorded else None,
    )


async def _load_latest(
    session: AsyncSession, source: str, sku: str | None = None
) -> dict[str, StockPosition]:
    latest = latest_snapshot_ids(source)
    query = select(InventorySnapshot).join(
        latest, InventorySnapshot.id == latest.c.max_id
    )
    if sku is not None:
        query = query.where(InventorySnapshot.sku == sku)
    result = await session.execute(query)
    grouped: dict[str, list[InventorySnapshot]] = defaultdict(list)
    for snap in result.scalars().all():
        grouped[snap.sku].append(snap)
    return {key: _combine(key, snaps) for key, snaps in grouped.items()}


async def positions_by_sku(
    session: AsyncSession, source: str = "shiphero"
) -> dict[str, StockPosition]:
    """Latest stock position for every SKU from ``source``."""
    return await _load_latest(session, source)


async def position_for_sku(
    session: AsyncSession, sku: str, source: str = "shiphero"
) -> StockPosition | None:
    """Latest stock position for one SKU, or None if it has no snapshots."""
    found = await _load_latest(session, source, sku=sku)
    return found.get(sku)
