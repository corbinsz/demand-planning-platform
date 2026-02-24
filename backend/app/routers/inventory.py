import logging
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import Product, InventorySnapshot, Order, OrderLineItem, ReorderRule
from app.services.reconciliation import reconcile_inventory, get_discrepancies

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
    db: AsyncSession = Depends(get_db),
):
    """Paginated SKU inventory with search, filters, and sorting."""
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
        .outerjoin(Product, InventorySnapshot.sku == Product.sku)
    )

    if search:
        query = query.where(
            InventorySnapshot.sku.ilike(f"%{search}%")
            | Product.title.ilike(f"%{search}%")
        )
    if warehouse:
        query = query.where(InventorySnapshot.warehouse == warehouse)
    if source:
        query = query.where(InventorySnapshot.source == source)

    # Count
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    # Sort
    sort_col = INVENTORY_SORT_COLUMNS.get(sort_by, InventorySnapshot.sku)
    order = sort_col.desc() if sort_dir == "desc" else sort_col.asc()

    # Paginate
    query = query.order_by(order).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    rows = result.all()

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
        for r in rows
    ]

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


@router.get("/reconciled")
async def reconciled_inventory():
    """Get unified inventory with Shopify/ShipHero reconciliation."""
    try:
        records = await reconcile_inventory()
    except Exception as e:
        logger.error(f"Inventory reconciliation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reconcile inventory: {e}")
    return {"items": [asdict(r) for r in records], "total": len(records)}


@router.get("/discrepancies")
async def inventory_discrepancies():
    """Get SKUs with inventory discrepancies between sources."""
    try:
        records = await get_discrepancies()
    except Exception as e:
        logger.error(f"Discrepancy check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check discrepancies: {e}")
    return {"items": [asdict(r) for r in records], "total": len(records)}


@router.get("/warehouses")
async def list_warehouses(db: AsyncSession = Depends(get_db)):
    """Get list of distinct warehouses."""
    result = await db.execute(
        select(InventorySnapshot.warehouse)
        .distinct()
        .where(InventorySnapshot.warehouse.isnot(None))
    )
    return {"warehouses": [r[0] for r in result.all()]}


@router.get("/sku/{sku}")
async def sku_detail(sku: str, db: AsyncSession = Depends(get_db)):
    """Full detail for a single SKU: product info, stock, sales, reorder rule."""
    # Product info
    prod_result = await db.execute(select(Product).where(Product.sku == sku))
    product = prod_result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail=f"SKU not found: {sku}")

    # Latest inventory snapshots (all sources)
    snap_result = await db.execute(
        select(InventorySnapshot)
        .where(InventorySnapshot.sku == sku)
        .order_by(InventorySnapshot.recorded_at.desc())
        .limit(20)
    )
    snapshots = snap_result.scalars().all()

    # Sales history (last 90 days)
    now = datetime.now(timezone.utc)
    ninety_days_ago = now - timedelta(days=90)
    sales_result = await db.execute(
        select(
            func.strftime('%Y-%m-%d', Order.created_at).label("date"),
            func.sum(OrderLineItem.quantity).label("units"),
            func.sum(OrderLineItem.price * OrderLineItem.quantity).label("revenue"),
        )
        .join(Order, OrderLineItem.order_id == Order.order_id)
        .where(OrderLineItem.sku == sku, Order.created_at >= ninety_days_ago)
        .group_by(func.strftime('%Y-%m-%d', Order.created_at))
        .order_by(func.strftime('%Y-%m-%d', Order.created_at))
    )
    sales_rows = sales_result.all()

    # Totals
    totals_result = await db.execute(
        select(
            func.coalesce(func.sum(OrderLineItem.quantity), 0),
            func.coalesce(func.sum(OrderLineItem.price * OrderLineItem.quantity), 0),
            func.count(func.distinct(Order.order_id)),
        )
        .join(Order, OrderLineItem.order_id == Order.order_id)
        .where(OrderLineItem.sku == sku, Order.created_at >= ninety_days_ago)
    )
    totals = totals_result.one()

    # Reorder rule
    rule_result = await db.execute(
        select(ReorderRule).where(ReorderRule.sku == sku)
    )
    rule = rule_result.scalar_one_or_none()

    # Current stock (latest shiphero snapshot)
    latest_snap = next((s for s in snapshots if s.source == "shiphero"), None)

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
            "on_hand": latest_snap.quantity_on_hand if latest_snap else 0,
            "allocated": latest_snap.quantity_allocated if latest_snap else 0,
            "available": latest_snap.quantity_available if latest_snap else 0,
            "warehouse": latest_snap.warehouse if latest_snap else None,
            "last_updated": latest_snap.recorded_at.isoformat() if latest_snap else None,
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
            "total_units": totals[0],
            "total_revenue": float(totals[1]),
            "total_orders": totals[2],
            "daily_avg": round(totals[0] / 90, 2) if totals[0] else 0,
            "timeline": [
                {"date": r[0], "units": r[1], "revenue": float(r[2]) if r[2] else 0}
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
