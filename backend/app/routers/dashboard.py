import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import Ctx, get_ctx
from app.models.models import JobLog, Order, OrderLineItem, Product
from app.services.forecasting import generate_all_forecasts
from app.services.stock import latest_snapshot_subquery, summed_stock
from app.sqlutil import day_key
from app.timeutil import utcnow_naive

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("")
async def get_dashboard(
    ctx: Ctx = Depends(get_ctx),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await _dashboard(db, ctx.workspace_id)
    except Exception:
        logger.exception("Dashboard query failed")
        raise HTTPException(status_code=500, detail="We couldn't load the dashboard.")


async def _dashboard(db: AsyncSession, workspace_id: int) -> dict:
    now = utcnow_naive()
    thirty = now - timedelta(days=30)
    ws = Product.workspace_id == workspace_id

    total_skus = int(await db.scalar(select(func.count(Product.id)).where(ws)) or 0)
    stock = await summed_stock(db, workspace_id, "shiphero")
    total_on_hand = sum(int(row["on_hand"]) for row in stock.values())
    total_available = sum(max(int(row["available"]), 0) for row in stock.values())

    orders_30d = int(await db.scalar(
        select(func.count(Order.id)).where(Order.workspace_id == workspace_id, Order.created_at >= thirty)
    ) or 0)
    revenue_30d = float(await db.scalar(
        select(func.coalesce(func.sum(Order.total_price), 0)).where(
            Order.workspace_id == workspace_id, Order.created_at >= thirty
        )
    ) or 0)
    units_30d = int(await db.scalar(
        select(func.coalesce(func.sum(OrderLineItem.quantity), 0))
        .join(Order, and_(Order.workspace_id == OrderLineItem.workspace_id, Order.order_id == OrderLineItem.order_id))
        .where(OrderLineItem.workspace_id == workspace_id, Order.created_at >= thirty)
    ) or 0)

    sell_through = 0.0
    if units_30d + total_on_hand > 0:
        sell_through = round(units_30d / (units_30d + total_on_hand) * 100, 1)

    # Inventory at cost uses available units, summed across warehouses.
    latest = latest_snapshot_subquery(workspace_id, "shiphero")
    from app.models.models import InventorySnapshot
    cost_value = await db.scalar(
        select(func.coalesce(func.sum(
            InventorySnapshot.quantity_available * func.coalesce(Product.cost_price, 0)
        ), 0))
        .join(latest, InventorySnapshot.id == latest.c.max_id)
        .outerjoin(
            Product,
            and_(Product.workspace_id == workspace_id, Product.sku == InventorySnapshot.sku),
        )
    )
    total_inventory_cost = round(float(cost_value or 0), 2)

    below_reorder = 0
    critical = 0
    try:
        forecasts, _ = await generate_all_forecasts(workspace_id)
        below_reorder = sum(1 for row in forecasts if row.below_reorder_point)
        critical = sum(
            1 for row in forecasts
            if row.days_of_stock_remaining is not None and row.days_of_stock_remaining <= row.lead_time_days
        )
    except Exception:
        logger.exception("Dashboard forecast summary failed")

    # Rough daily revenue currently earned by SKUs that are now unavailable.
    oos_skus = [sku for sku, row in stock.items() if int(row["available"]) <= 0]
    oos_rev = 0.0
    if oos_skus:
        oos_rev = float(await db.scalar(
            select(func.coalesce(func.sum(OrderLineItem.quantity * OrderLineItem.price), 0))
            .join(Order, and_(Order.workspace_id == OrderLineItem.workspace_id, Order.order_id == OrderLineItem.order_id))
            .where(
                OrderLineItem.workspace_id == workspace_id,
                Order.created_at >= thirty,
                OrderLineItem.sku.in_(oos_skus),
            )
        ) or 0)
    revenue_at_risk_daily = round(oos_rev / 30, 2) if oos_rev > 0 else 0

    last_job = (await db.execute(
        select(JobLog)
        .where(JobLog.workspace_id == workspace_id)
        .order_by(JobLog.started_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    return {
        "total_skus": total_skus,
        "total_on_hand_units": total_on_hand,
        "total_available_units": total_available,
        "orders_last_30d": orders_30d,
        "revenue_last_30d": round(revenue_30d, 2),
        "units_sold_last_30d": units_30d,
        "skus_below_reorder": below_reorder,
        "skus_stockout_risk": critical,
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
    ctx: Ctx = Depends(get_ctx),
    db: AsyncSession = Depends(get_db),
):
    try:
        start = utcnow_naive() - timedelta(days=days)
        day = day_key(Order.created_at)
        result = await db.execute(
            select(
                day.label("date"),
                func.count(func.distinct(Order.id)).label("orders"),
                func.coalesce(func.sum(Order.total_price), 0).label("revenue"),
                func.coalesce(func.sum(OrderLineItem.quantity), 0).label("units"),
            )
            .join(
                OrderLineItem,
                and_(Order.workspace_id == OrderLineItem.workspace_id, Order.order_id == OrderLineItem.order_id),
                isouter=True,
            )
            .where(Order.workspace_id == ctx.workspace_id, Order.created_at >= start)
            .group_by(day)
            .order_by(day)
        )
        return {
            "items": [
                {"date": str(r[0]), "orders": r[1], "revenue": float(r[2]), "units": int(r[3])}
                for r in result.all()
            ]
        }
    except Exception:
        logger.exception("Sales trend query failed")
        raise HTTPException(status_code=500, detail="We couldn't load the sales trend.")
