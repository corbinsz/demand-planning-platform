import logging
from dataclasses import asdict
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import Ctx, get_ctx
from app.models.models import InventorySnapshot, Order, OrderLineItem, Product, ReorderRule
from app.services.reconciliation import get_discrepancies, reconcile_inventory
from app.services.stock import latest_snapshot_subquery, summed_stock
from app.sqlutil import day_key, like_contains
from app.timeutil import utcnow_naive

logger = logging.getLogger(__name__)
router = APIRouter()

INVENTORY_SORT_COLUMNS = {
    "sku": InventorySnapshot.sku,
    "title": Product.title,
    "quantity_on_hand": InventorySnapshot.quantity_on_hand,
    "quantity_available": InventorySnapshot.quantity_available,
    "warehouse": InventorySnapshot.warehouse,
    "recorded_at": InventorySnapshot.recorded_at,
}


@router.get("")
async def list_inventory(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    search: str = Query(None),
    warehouse: str = Query(None),
    source: str = Query(None),
    sort_by: str = Query("sku"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    ctx: Ctx = Depends(get_ctx),
    db: AsyncSession = Depends(get_db),
):
    """Current stock: the latest snapshot per SKU, warehouse, and source."""
    latest = latest_snapshot_subquery(ctx.workspace_id, source)
    query = (
        select(
            InventorySnapshot.sku,
            Product.title,
            InventorySnapshot.quantity_on_hand,
            InventorySnapshot.quantity_allocated,
            InventorySnapshot.quantity_available,
            InventorySnapshot.warehouse,
            InventorySnapshot.source,
            InventorySnapshot.recorded_at,
            Product.image_url,
            Product.cost_price,
            Product.parent_sku,
        )
        .join(latest, InventorySnapshot.id == latest.c.max_id)
        .outerjoin(
            Product,
            and_(Product.workspace_id == ctx.workspace_id, Product.sku == InventorySnapshot.sku),
        )
    )
    if search:
        pattern = like_contains(search.strip())
        query = query.where(
            InventorySnapshot.sku.ilike(pattern, escape="\\")
            | Product.title.ilike(pattern, escape="\\")
        )
    if warehouse:
        query = query.where(InventorySnapshot.warehouse == warehouse)
    if source:
        query = query.where(InventorySnapshot.source == source)

    total = int(await db.scalar(select(func.count()).select_from(query.subquery())) or 0)
    sort_col = INVENTORY_SORT_COLUMNS.get(sort_by, InventorySnapshot.sku)
    order = sort_col.desc() if sort_dir == "desc" else sort_col.asc()
    result = await db.execute(query.order_by(order).offset((page - 1) * per_page).limit(per_page))
    items = [
        {
            "sku": r[0],
            "title": r[1] or "Unknown",
            "quantity_on_hand": r[2],
            "quantity_allocated": r[3],
            "quantity_available": r[4],
            "warehouse": r[5],
            "source": r[6],
            "recorded_at": r[7].isoformat() if r[7] else None,
            "image_url": r[8],
            "cost_price": float(r[9]) if r[9] else None,
            "parent_sku": r[10],
        }
        for r in result.all()
    ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page else 0,
    }


@router.get("/reconciled")
async def reconciled_inventory(ctx: Ctx = Depends(get_ctx)):
    try:
        records = await reconcile_inventory(ctx.workspace_id)
    except Exception:
        logger.exception("Inventory reconciliation failed")
        raise HTTPException(status_code=500, detail="We couldn't reconcile inventory.")
    return {"items": [asdict(r) for r in records], "total": len(records)}


@router.get("/discrepancies")
async def inventory_discrepancies(ctx: Ctx = Depends(get_ctx)):
    try:
        records = await get_discrepancies(ctx.workspace_id)
    except Exception:
        logger.exception("Discrepancy check failed")
        raise HTTPException(status_code=500, detail="We couldn't check discrepancies.")
    return {"items": [asdict(r) for r in records], "total": len(records)}


@router.get("/warehouses")
async def list_warehouses(ctx: Ctx = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(InventorySnapshot.warehouse)
        .distinct()
        .where(
            InventorySnapshot.workspace_id == ctx.workspace_id,
            InventorySnapshot.warehouse.isnot(None),
        )
    )
    return {"warehouses": [r[0] for r in result.all()]}


@router.get("/sku/{sku}")
async def sku_detail(sku: str, ctx: Ctx = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    product = (await db.execute(
        select(Product).where(Product.workspace_id == ctx.workspace_id, Product.sku == sku)
    )).scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="SKU not found.")

    snapshots = (await db.execute(
        select(InventorySnapshot)
        .where(InventorySnapshot.workspace_id == ctx.workspace_id, InventorySnapshot.sku == sku)
        .order_by(InventorySnapshot.recorded_at.desc())
        .limit(20)
    )).scalars().all()

    ninety = utcnow_naive() - timedelta(days=90)
    day = day_key(Order.created_at)
    sales_rows = (await db.execute(
        select(
            day.label("date"),
            func.sum(OrderLineItem.quantity),
            func.sum(OrderLineItem.price * OrderLineItem.quantity),
        )
        .join(Order, and_(Order.workspace_id == OrderLineItem.workspace_id, Order.order_id == OrderLineItem.order_id))
        .where(
            OrderLineItem.workspace_id == ctx.workspace_id,
            OrderLineItem.sku == sku,
            Order.created_at >= ninety,
        )
        .group_by(day)
        .order_by(day)
    )).all()
    totals = (await db.execute(
        select(
            func.coalesce(func.sum(OrderLineItem.quantity), 0),
            func.coalesce(func.sum(OrderLineItem.price * OrderLineItem.quantity), 0),
            func.count(func.distinct(Order.order_id)),
        )
        .join(Order, and_(Order.workspace_id == OrderLineItem.workspace_id, Order.order_id == OrderLineItem.order_id))
        .where(
            OrderLineItem.workspace_id == ctx.workspace_id,
            OrderLineItem.sku == sku,
            Order.created_at >= ninety,
        )
    )).one()
    rule = (await db.execute(
        select(ReorderRule).where(ReorderRule.workspace_id == ctx.workspace_id, ReorderRule.sku == sku)
    )).scalar_one_or_none()
    stock = await summed_stock(db, ctx.workspace_id, "shiphero")
    current = stock.get(sku) or {"on_hand": 0, "allocated": 0, "available": 0, "warehouses": [], "recorded_at": None}

    return {
        "sku": sku,
        "title": product.title,
        "image_url": product.image_url,
        "cost_price": float(product.cost_price) if product.cost_price else None,
        "parent_sku": product.parent_sku,
        "shopify_id": product.shopify_id,
        "shiphero_id": product.shiphero_id,
        "created_at": product.created_at.isoformat() if product.created_at else None,
        "current_stock": {
            "on_hand": current["on_hand"],
            "allocated": current["allocated"],
            "available": current["available"],
            "warehouse": ", ".join(current["warehouses"]) or None,
            "last_updated": current["recorded_at"].isoformat() if current["recorded_at"] else None,
        },
        "stock_history": [
            {
                "source": s.source,
                "on_hand": s.quantity_on_hand,
                "allocated": s.quantity_allocated,
                "available": s.quantity_available,
                "warehouse": s.warehouse,
                "recorded_at": s.recorded_at.isoformat() if s.recorded_at else None,
            }
            for s in snapshots
        ],
        "sales_90d": {
            "total_units": int(totals[0]),
            "total_revenue": float(totals[1] or 0),
            "total_orders": int(totals[2]),
            "daily_avg": round(int(totals[0]) / 90, 2) if totals[0] else 0,
            "timeline": [
                {"date": str(r[0]), "units": int(r[1] or 0), "revenue": float(r[2] or 0)}
                for r in sales_rows
            ],
        },
        "reorder_rule": {
            "reorder_point": rule.reorder_point,
            "reorder_quantity": rule.reorder_quantity,
            "lead_time_days": rule.lead_time_days,
            "safety_stock": rule.safety_stock,
        } if rule else None,
    }
