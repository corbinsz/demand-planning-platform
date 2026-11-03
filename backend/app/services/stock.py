"""Current stock = latest snapshot per warehouse, then summed.

Older code summed every historical snapshot (forecasts inflated) or kept
only the single newest row (the second warehouse disappeared).
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import InventorySnapshot


def latest_snapshot_subquery(workspace_id: int, source: str | None = None):
    filters = [InventorySnapshot.workspace_id == workspace_id]
    if source is not None:
        filters.append(InventorySnapshot.source == source)
    return (
        select(
            InventorySnapshot.sku.label("sku"),
            InventorySnapshot.warehouse.label("warehouse"),
            InventorySnapshot.source.label("source"),
            func.max(InventorySnapshot.id).label("max_id"),
        )
        .where(*filters)
        .group_by(InventorySnapshot.sku, InventorySnapshot.warehouse, InventorySnapshot.source)
        .subquery()
    )


async def summed_stock(
    session: AsyncSession,
    workspace_id: int,
    source: str,
) -> dict[str, dict]:
    """sku -> on_hand, allocated, available, warehouses (list)."""
    latest = latest_snapshot_subquery(workspace_id, source)
    result = await session.execute(
        select(
            InventorySnapshot.sku,
            InventorySnapshot.warehouse,
            InventorySnapshot.quantity_on_hand,
            InventorySnapshot.quantity_allocated,
            InventorySnapshot.quantity_available,
            InventorySnapshot.recorded_at,
        ).join(latest, InventorySnapshot.id == latest.c.max_id)
    )
    out: dict[str, dict] = {}
    for sku, warehouse, on_hand, allocated, available, recorded_at in result.all():
        row = out.setdefault(
            sku,
            {
                "on_hand": 0,
                "allocated": 0,
                "available": 0,
                "warehouses": [],
                "recorded_at": None,
            },
        )
        row["on_hand"] += int(on_hand or 0)
        row["allocated"] += int(allocated or 0)
        row["available"] += int(available or 0)
        if warehouse and warehouse not in row["warehouses"]:
            row["warehouses"].append(warehouse)
        if recorded_at is not None and (row["recorded_at"] is None or recorded_at > row["recorded_at"]):
            row["recorded_at"] = recorded_at
    return out
