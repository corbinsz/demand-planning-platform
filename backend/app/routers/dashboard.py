import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import (
    Product,
    Order,
    OrderLineItem,
    InventorySnapshot,
    ReorderRule,
    JobLog,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("")
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    """KPI summary for the dashboard."""
    try:
        return await _get_dashboard_data(db)
    except Exception as e:
        logger.error(f"Dashboard query failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load dashboard: {e}")


async def _get_dashboard_data(db: AsyncSession):
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)

    # Total active SKUs
    total_skus = await db.execute(select(func.count(Product.id)))
    total_skus = total_skus.scalar_one()

    # Total inventory on hand — latest snapshot per SKU only
    latest_sub = (
        select(
            InventorySnapshot.sku,
            func.max(InventorySnapshot.id).label("max_id"),
        )
        .where(InventorySnapshot.source == "shiphero")
        .group_by(InventorySnapshot.sku)
        .subquery()
    )
    total_on_hand = await db.execute(
        select(func.coalesce(func.sum(InventorySnapshot.quantity_on_hand), 0))
        .join(latest_sub, InventorySnapshot.id == latest_sub.c.max_id)
    )
    total_on_hand = int(total_on_hand.scalar_one())

    # Orders last 30 days
    orders_30d = await db.execute(
        select(func.count(Order.id)).where(Order.created_at >= thirty_days_ago)
    )
    orders_30d = orders_30d.scalar_one()

    # Revenue last 30 days
    revenue_30d = await db.execute(
        select(func.coalesce(func.sum(Order.total_price), 0)).where(
            Order.created_at >= thirty_days_ago
        )
    )
    revenue_30d = float(revenue_30d.scalar_one())

    # Units sold last 30 days
    units_30d = await db.execute(
        select(func.coalesce(func.sum(OrderLineItem.quantity), 0))
        .join(Order, OrderLineItem.order_id == Order.order_id)
        .where(Order.created_at >= thirty_days_ago)
    )
    units_30d = int(units_30d.scalar_one())

    # SKUs below reorder point — use DISTINCT to avoid double-counting from multiple snapshots
    below_reorder = await db.execute(
        select(func.count(func.distinct(ReorderRule.sku)))
        .join(InventorySnapshot, ReorderRule.sku == InventorySnapshot.sku)
        .where(
            and_(
                InventorySnapshot.source == "shiphero",
                InventorySnapshot.quantity_available < ReorderRule.reorder_point,
                ReorderRule.reorder_point > 0,
            )
        )
    )
    below_reorder = below_reorder.scalar_one()

    # Last sync status
    last_job = await db.execute(
        select(JobLog)
        .order_by(JobLog.started_at.desc())
        .limit(1)
    )
    last_job = last_job.scalar_one_or_none()

    # Sell-through rate: units sold / (units sold + current stock)
    sell_through = 0
    if units_30d + total_on_hand > 0:
        sell_through = round(units_30d / (units_30d + total_on_hand) * 100, 1)

    # Revenue at Risk: daily revenue lost from out-of-stock SKUs
    # Find SKUs with 0 available stock that had sales in last 90 days
    oos_velocity = await db.execute(
        select(
            func.coalesce(
                func.sum(OrderLineItem.quantity * OrderLineItem.price),
                0,
            )
        )
        .join(Order, OrderLineItem.order_id == Order.order_id)
        .join(
            latest_sub,
            and_(
                OrderLineItem.sku == latest_sub.c.sku,
            ),
        )
        .join(
            InventorySnapshot,
            InventorySnapshot.id == latest_sub.c.max_id,
        )
        .where(
            Order.created_at >= thirty_days_ago,
            InventorySnapshot.quantity_available <= 0,
        )
    )
    oos_rev_30d = float(oos_velocity.scalar_one())
    revenue_at_risk_daily = round(oos_rev_30d / 30, 2) if oos_rev_30d > 0 else 0

    # Total inventory value (stock × avg selling price per SKU)
    inv_value_result = await db.execute(
        select(
            func.coalesce(
                func.sum(InventorySnapshot.quantity_available * func.coalesce(Product.cost_price, 0)),
                0,
            )
        )
        .join(latest_sub, InventorySnapshot.id == latest_sub.c.max_id)
        .outerjoin(Product, InventorySnapshot.sku == Product.sku)
    )
    total_inventory_cost = round(float(inv_value_result.scalar_one()), 2)

    return {
        "total_skus": total_skus,
        "total_on_hand_units": total_on_hand,
        "orders_last_30d": orders_30d,
        "revenue_last_30d": revenue_30d,
        "units_sold_last_30d": units_30d,
        "skus_below_reorder": below_reorder,
        "sell_through_rate": sell_through,
        "revenue_at_risk_daily": revenue_at_risk_daily,
        "total_inventory_cost": total_inventory_cost,
        "last_sync": {
            "job": last_job.job_name if last_job else None,
            "status": last_job.status if last_job else None,
            "at": last_job.finished_at.isoformat() if last_job and last_job.finished_at else None,
        },
    }


@router.get("/sales-trend")
async def sales_trend(
    days: int = Query(30, ge=7, le=90),
    db: AsyncSession = Depends(get_db),
):
    """Daily sales trend for dashboard chart."""
    try:
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=days)

        result = await db.execute(
            select(
                func.strftime('%Y-%m-%d', Order.created_at).label("date"),
                func.count(func.distinct(Order.id)).label("orders"),
                func.coalesce(func.sum(Order.total_price), 0).label("revenue"),
                func.coalesce(func.sum(OrderLineItem.quantity), 0).label("units"),
            )
            .join(OrderLineItem, Order.order_id == OrderLineItem.order_id, isouter=True)
            .where(Order.created_at >= start)
            .group_by(func.strftime('%Y-%m-%d', Order.created_at))
            .order_by(func.strftime('%Y-%m-%d', Order.created_at))
        )
        rows = result.all()

        return {
            "items": [
                {"date": r[0], "orders": r[1], "revenue": float(r[2]), "units": int(r[3])}
                for r in rows
            ]
        }
    except Exception as e:
        logger.error(f"Sales trend query failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load sales trend: {e}")
