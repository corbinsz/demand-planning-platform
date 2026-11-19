"""Dashboard KPIs and the daily sales chart."""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import day_bucket, get_db
from app.models.models import JobLog, Order, OrderLineItem, Product
from app.services.forecasting import get_reorder_alerts
from app.services.stock import positions_by_sku
from app.timeutil import as_date_str

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("")
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    """KPI summary for the home page."""
    try:
        return await _get_dashboard_data(db)
    except Exception as exc:
        logger.exception("Dashboard query failed")
        raise HTTPException(
            status_code=500, detail=f"Failed to load dashboard: {exc}"
        ) from exc


async def _get_dashboard_data(db: AsyncSession) -> dict:
    now = datetime.now(UTC)
    thirty_days_ago = now - timedelta(days=30)

    total_skus = (await db.execute(select(func.count(Product.id)))).scalar_one()
    positions = await positions_by_sku(db, "shiphero")
    total_on_hand = sum(position.on_hand for position in positions.values())

    orders_30d = (
        await db.execute(
            select(func.count(Order.id)).where(Order.created_at >= thirty_days_ago)
        )
    ).scalar_one()
    revenue_30d = float(
        (
            await db.execute(
                select(func.coalesce(func.sum(Order.total_price), 0)).where(
                    Order.created_at >= thirty_days_ago
                )
            )
        ).scalar_one()
        or 0
    )
    units_30d = int(
        (
            await db.execute(
                select(func.coalesce(func.sum(OrderLineItem.quantity), 0))
                .join(Order, OrderLineItem.order_id == Order.order_id)
                .where(Order.created_at >= thirty_days_ago)
            )
        ).scalar_one()
    )

    # Same definition as the alert list: stock at or under the forecast reorder point.
    below_reorder = len(await get_reorder_alerts())

    last_job = (
        await db.execute(select(JobLog).order_by(JobLog.started_at.desc()).limit(1))
    ).scalar_one_or_none()

    sell_through = 0.0
    if units_30d + total_on_hand > 0:
        sell_through = round(units_30d / (units_30d + total_on_hand) * 100, 1)

    out_of_stock = [
        sku for sku, position in positions.items() if position.available <= 0
    ]
    revenue_at_risk_daily = 0.0
    if out_of_stock:
        oos_rev_30d = float(
            (
                await db.execute(
                    select(
                        func.coalesce(
                            func.sum(OrderLineItem.quantity * OrderLineItem.price), 0
                        )
                    )
                    .join(Order, OrderLineItem.order_id == Order.order_id)
                    .where(
                        Order.created_at >= thirty_days_ago,
                        OrderLineItem.sku.in_(out_of_stock),
                    )
                )
            ).scalar_one()
        )
        revenue_at_risk_daily = round(oos_rev_30d / 30, 2) if oos_rev_30d > 0 else 0.0

    costs = await db.execute(select(Product.sku, Product.cost_price))
    cost_map = {sku: float(cost or 0) for sku, cost in costs.all()}
    total_inventory_cost = round(
        sum(
            position.available * cost_map.get(sku, 0.0)
            for sku, position in positions.items()
        ),
        2,
    )

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
            "at": (
                last_job.finished_at.isoformat()
                if last_job and last_job.finished_at
                else None
            ),
        },
    }


@router.get("/sales-trend")
async def sales_trend(
    days: int = Query(30, ge=7, le=90),
    db: AsyncSession = Depends(get_db),
):
    """Daily orders, revenue, and units.

    Revenue is the order total, summed once per order. Joining line items
    in the same query would multiply that total by the number of lines.
    """
    try:
        start = datetime.now(UTC) - timedelta(days=days)
        units = (
            select(
                OrderLineItem.order_id.label("order_id"),
                func.sum(OrderLineItem.quantity).label("units"),
            )
            .group_by(OrderLineItem.order_id)
            .subquery()
        )
        day = day_bucket(Order.created_at)
        result = await db.execute(
            select(
                day.label("date"),
                func.count(Order.id).label("orders"),
                func.coalesce(func.sum(Order.total_price), 0).label("revenue"),
                func.coalesce(func.sum(units.c.units), 0).label("units"),
            )
            .outerjoin(units, units.c.order_id == Order.order_id)
            .where(Order.created_at >= start)
            .group_by(day)
            .order_by(day)
        )
        return {
            "items": [
                {
                    "date": as_date_str(row[0]),
                    "orders": row[1],
                    "revenue": float(row[2]),
                    "units": int(row[3]),
                }
                for row in result.all()
            ]
        }
    except Exception as exc:
        logger.exception("Sales trend query failed")
        raise HTTPException(
            status_code=500, detail=f"Failed to load sales trend: {exc}"
        ) from exc
