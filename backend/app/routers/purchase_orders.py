import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import ReorderRule, Product
from app.services.forecasting import get_reorder_alerts
from app.services.shiphero_sync import fetch_open_purchase_orders

logger = logging.getLogger(__name__)


class ReorderRuleUpdate(BaseModel):
    reorder_point: int = Field(ge=0)
    reorder_quantity: int = Field(ge=1)
    lead_time_days: int = Field(ge=1, le=365)
    safety_stock: int = Field(ge=0)

router = APIRouter()


@router.get("")
async def list_purchase_orders():
    """Get open purchase orders from ShipHero."""
    try:
        pos = await fetch_open_purchase_orders()
    except Exception as e:
        logger.error(f"Failed to fetch POs from ShipHero: {e}")
        error_msg = str(e)
        if "401" in error_msg or "UNAUTHORIZED" in error_msg.upper():
            return {"items": [], "total": 0, "error": "ShipHero authentication failed. Check your API token in Setup."}
        return {"items": [], "total": 0, "error": f"Failed to fetch from ShipHero: {error_msg}"}
    return {"items": pos, "total": len(pos)}


@router.get("/suggestions")
async def po_suggestions():
    """Generate purchase order suggestions based on reorder alerts."""
    try:
        alerts = await get_reorder_alerts()
    except Exception as e:
        logger.error(f"Failed to generate PO suggestions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate suggestions: {e}")

    suggestions = []
    for alert in alerts:
        suggestions.append({
            "sku": alert.sku,
            "title": alert.title,
            "current_stock": alert.current_stock,
            "reorder_point": alert.reorder_point,
            "suggested_quantity": alert.suggested_reorder_qty,
            "daily_velocity": alert.rolling_30d_avg,
            "days_of_stock_remaining": alert.days_of_stock_remaining,
            "lead_time_days": alert.lead_time_days,
            "urgency": _calculate_urgency(alert.days_of_stock_remaining, alert.lead_time_days),
        })

    # Sort by urgency (critical first)
    priority = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    suggestions.sort(key=lambda x: priority.get(x["urgency"], 99))

    return {"items": suggestions, "total": len(suggestions)}


@router.get("/rules")
async def list_reorder_rules(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List all reorder rules."""
    count_q = select(func.count(ReorderRule.id))
    total = (await db.execute(count_q)).scalar_one()

    query = (
        select(ReorderRule, Product.title)
        .outerjoin(Product, ReorderRule.sku == Product.sku)
        .order_by(ReorderRule.sku)
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(query)
    rows = result.all()

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
        "pages": (total + per_page - 1) // per_page,
    }


@router.put("/rules/{sku}")
async def update_reorder_rule(
    sku: str,
    body: ReorderRuleUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update or create a reorder rule for a SKU."""
    result = await db.execute(select(ReorderRule).where(ReorderRule.sku == sku))
    rule = result.scalar_one_or_none()

    if rule:
        rule.reorder_point = body.reorder_point
        rule.reorder_quantity = body.reorder_quantity
        rule.lead_time_days = body.lead_time_days
        rule.safety_stock = body.safety_stock
    else:
        rule = ReorderRule(
            sku=sku,
            reorder_point=body.reorder_point,
            reorder_quantity=body.reorder_quantity,
            lead_time_days=body.lead_time_days,
            safety_stock=body.safety_stock,
        )
        db.add(rule)

    await db.commit()
    return {
        "sku": sku,
        "reorder_point": rule.reorder_point,
        "reorder_quantity": rule.reorder_quantity,
        "lead_time_days": rule.lead_time_days,
        "safety_stock": rule.safety_stock,
    }


def _calculate_urgency(days_remaining: float | None, lead_time: int) -> str:
    """Calculate urgency level for reorder."""
    if days_remaining is None or days_remaining <= 0:
        return "critical"
    if days_remaining <= lead_time:
        return "critical"
    if days_remaining <= lead_time * 1.5:
        return "high"
    if days_remaining <= lead_time * 2:
        return "medium"
    return "low"
