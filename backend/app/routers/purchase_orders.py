import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import Ctx, get_ctx
from app.models.models import Product, ReorderRule
from app.services.credentials import get_shiphero_auth
from app.services.forecasting import get_reorder_alerts
from app.services.reorder import urgency
from app.services.shiphero_sync import open_purchase_orders

logger = logging.getLogger(__name__)
router = APIRouter()


class ReorderRuleUpdate(BaseModel):
    reorder_point: int = Field(ge=0)
    reorder_quantity: int = Field(ge=1)
    lead_time_days: int = Field(ge=1, le=365)
    safety_stock: int = Field(ge=0)


@router.get("")
async def list_purchase_orders(ctx: Ctx = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    """Open purchase orders from ShipHero, when this workspace is connected."""
    auth = await get_shiphero_auth(db, ctx.workspace_id)
    if auth is None:
        return {
            "items": [],
            "total": 0,
            "notice": "ShipHero is not connected. The What to buy tab is based on your order history.",
        }
    try:
        pos = await open_purchase_orders(auth.access_token)
    except Exception:
        logger.exception("Failed to fetch POs from ShipHero")
        return {"items": [], "total": 0, "notice": "ShipHero didn't respond. Check the connection and try again."}
    return {"items": pos, "total": len(pos)}


@router.get("/suggestions")
async def po_suggestions(ctx: Ctx = Depends(get_ctx)):
    try:
        alerts = await get_reorder_alerts(ctx.workspace_id)
    except Exception:
        logger.exception("Failed to generate PO suggestions")
        raise HTTPException(status_code=500, detail="We couldn't build reorder suggestions.")
    suggestions = [
        {
            "sku": alert.sku,
            "title": alert.title,
            "current_stock": alert.current_stock,
            "reorder_point": alert.reorder_point,
            "suggested_quantity": alert.suggested_reorder_qty,
            "daily_velocity": alert.rolling_30d_avg,
            "days_of_stock_remaining": alert.days_of_stock_remaining,
            "lead_time_days": alert.lead_time_days,
            "model": alert.model,
            "confidence_low_30": alert.confidence_low_30,
            "confidence_high_30": alert.confidence_high_30,
            "urgency": urgency(alert.days_of_stock_remaining, alert.lead_time_days),
        }
        for alert in alerts
        if alert.suggested_reorder_qty > 0
    ]
    priority = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    suggestions.sort(key=lambda row: priority.get(str(row["urgency"]), 99))
    return {"items": suggestions, "total": len(suggestions)}


@router.get("/rules")
async def list_reorder_rules(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    ctx: Ctx = Depends(get_ctx),
    db: AsyncSession = Depends(get_db),
):
    total = int(await db.scalar(
        select(func.count(ReorderRule.id)).where(ReorderRule.workspace_id == ctx.workspace_id)
    ) or 0)
    rows = (await db.execute(
        select(ReorderRule, Product.title)
        .outerjoin(Product, and_product(ctx.workspace_id))
        .where(ReorderRule.workspace_id == ctx.workspace_id)
        .order_by(ReorderRule.sku)
        .offset((page - 1) * per_page)
        .limit(per_page)
    )).all()
    # The join above is rewritten below if SQLAlchemy rejects the helper.
    return _rules_page(rows, total, page, per_page)


def and_product(workspace_id: int):
    return (Product.workspace_id == workspace_id) & (ReorderRule.sku == Product.sku)


def _rules_page(rows, total, page, per_page):
    items = [
        {
            "sku": rule.sku,
            "title": title or "Unknown",
            "reorder_point": rule.reorder_point,
            "reorder_quantity": rule.reorder_quantity,
            "lead_time_days": rule.lead_time_days,
            "safety_stock": rule.safety_stock,
        }
        for rule, title in rows
    ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page else 0,
    }


@router.put("/rules/{sku}")
async def update_reorder_rule(
    sku: str,
    body: ReorderRuleUpdate,
    ctx: Ctx = Depends(get_ctx),
    db: AsyncSession = Depends(get_db),
):
    product = (await db.execute(
        select(Product.id).where(Product.workspace_id == ctx.workspace_id, Product.sku == sku)
    )).scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="That SKU is not in this workspace.")
    rule = (await db.execute(
        select(ReorderRule).where(ReorderRule.workspace_id == ctx.workspace_id, ReorderRule.sku == sku)
    )).scalar_one_or_none()
    if rule is None:
        rule = ReorderRule(workspace_id=ctx.workspace_id, sku=sku, reorder_point=body.reorder_point, reorder_quantity=body.reorder_quantity)
        db.add(rule)
    rule.reorder_point = body.reorder_point
    rule.reorder_quantity = body.reorder_quantity
    rule.lead_time_days = body.lead_time_days
    rule.safety_stock = body.safety_stock
    from app.services.forecasting import invalidate_forecast_cache
    invalidate_forecast_cache(ctx.workspace_id)
    return {
        "sku": sku,
        "reorder_point": rule.reorder_point,
        "reorder_quantity": rule.reorder_quantity,
        "lead_time_days": rule.lead_time_days,
        "safety_stock": rule.safety_stock,
    }
