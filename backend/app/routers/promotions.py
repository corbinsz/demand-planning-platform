"""Promotional periods. Stored for the calendar; not yet applied to forecasts."""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import PromotionalPeriod
from app.timeutil import as_utc, is_active_window

logger = logging.getLogger(__name__)

router = APIRouter()


def _reject_inverted_window(start: datetime, end: datetime) -> None:
    """Promotions have to end on or after they start."""
    if as_utc(end) < as_utc(start):
        raise HTTPException(
            status_code=422, detail="end_date must be on or after start_date"
        )


class PromotionCreate(BaseModel):
    name: str
    start_date: datetime
    end_date: datetime
    discount_pct: float = 0
    notes: str | None = None


class PromotionUpdate(BaseModel):
    name: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    discount_pct: float | None = None
    notes: str | None = None


@router.get("")
async def list_promotions(
    active_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """List all promotional periods."""
    query = select(PromotionalPeriod).order_by(PromotionalPeriod.start_date.desc())
    if active_only:
        now = datetime.now(UTC)
        query = query.where(
            PromotionalPeriod.start_date <= now,
            PromotionalPeriod.end_date >= now,
        )
    result = await db.execute(query)
    items = result.scalars().all()
    return {
        "items": [
            {
                "id": p.id,
                "name": p.name,
                "start_date": p.start_date.isoformat() if p.start_date else None,
                "end_date": p.end_date.isoformat() if p.end_date else None,
                "discount_pct": p.discount_pct,
                "notes": p.notes,
                "is_active": (
                    is_active_window(p.start_date, p.end_date)
                    if p.start_date and p.end_date
                    else False
                ),
            }
            for p in items
        ],
        "total": len(items),
    }


@router.post("")
async def create_promotion(body: PromotionCreate, db: AsyncSession = Depends(get_db)):
    """Create a new promotional period."""
    _reject_inverted_window(body.start_date, body.end_date)
    promo = PromotionalPeriod(
        name=body.name,
        start_date=body.start_date,
        end_date=body.end_date,
        discount_pct=body.discount_pct,
        notes=body.notes,
    )
    db.add(promo)
    await db.commit()
    await db.refresh(promo)
    return {"id": promo.id, "name": promo.name}


@router.put("/{promo_id}")
async def update_promotion(
    promo_id: int, body: PromotionUpdate, db: AsyncSession = Depends(get_db)
):
    """Update a promotional period."""
    result = await db.execute(
        select(PromotionalPeriod).where(PromotionalPeriod.id == promo_id)
    )
    promo = result.scalar_one_or_none()
    if not promo:
        raise HTTPException(status_code=404, detail="Promotion not found")
    updates = body.model_dump(exclude_unset=True)
    new_start = updates.get("start_date", promo.start_date)
    new_end = updates.get("end_date", promo.end_date)
    if new_start and new_end:
        _reject_inverted_window(new_start, new_end)
    for field, value in updates.items():
        setattr(promo, field, value)
    logger.info("Updated promotion %s", promo.id)
    await db.commit()
    return {"id": promo.id, "name": promo.name}


@router.delete("/{promo_id}")
async def delete_promotion(promo_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a promotional period."""
    result = await db.execute(
        select(PromotionalPeriod).where(PromotionalPeriod.id == promo_id)
    )
    promo = result.scalar_one_or_none()
    if not promo:
        raise HTTPException(status_code=404, detail="Promotion not found")
    await db.delete(promo)
    await db.commit()
    return {"deleted": True}
