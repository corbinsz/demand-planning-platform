from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import Ctx, get_ctx
from app.models.models import PromotionalPeriod
from app.services.forecasting import invalidate_forecast_cache
from app.timeutil import utcnow_naive

router = APIRouter()


class PromotionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    start_date: object
    end_date: object
    discount_pct: float = Field(default=0, ge=0, le=100)
    notes: str | None = Field(default=None, max_length=2000)


class PromotionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    start_date: object | None = None
    end_date: object | None = None
    discount_pct: float | None = Field(default=None, ge=0, le=100)
    notes: str | None = Field(default=None, max_length=2000)


def _as_pair(start, end):
    from datetime import datetime
    if isinstance(start, str):
        start = datetime.fromisoformat(start.replace("Z", "+00:00"))
    if isinstance(end, str):
        end = datetime.fromisoformat(end.replace("Z", "+00:00"))
    if getattr(start, "tzinfo", None):
        start = start.replace(tzinfo=None)
    if getattr(end, "tzinfo", None):
        end = end.replace(tzinfo=None)
    if end < start:
        raise HTTPException(status_code=422, detail="The end date has to be on or after the start date.")
    return start, end


def _pack(promo: PromotionalPeriod) -> dict:
    now = utcnow_naive()
    return {
        "id": promo.id,
        "name": promo.name,
        "start_date": promo.start_date.isoformat() if promo.start_date else None,
        "end_date": promo.end_date.isoformat() if promo.end_date else None,
        "discount_pct": promo.discount_pct,
        "notes": promo.notes,
        "is_active": bool(promo.start_date and promo.end_date and promo.start_date <= now <= promo.end_date),
    }


@router.get("")
async def list_promotions(
    active_only: bool = Query(False),
    ctx: Ctx = Depends(get_ctx),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(PromotionalPeriod)
        .where(PromotionalPeriod.workspace_id == ctx.workspace_id)
        .order_by(PromotionalPeriod.start_date.desc())
    )
    if active_only:
        now = utcnow_naive()
        query = query.where(PromotionalPeriod.start_date <= now, PromotionalPeriod.end_date >= now)
    items = (await db.execute(query)).scalars().all()
    return {"items": [_pack(p) for p in items], "total": len(items)}


@router.post("")
async def create_promotion(
    body: PromotionCreate,
    ctx: Ctx = Depends(get_ctx),
    db: AsyncSession = Depends(get_db),
):
    start, end = _as_pair(body.start_date, body.end_date)
    promo = PromotionalPeriod(
        workspace_id=ctx.workspace_id,
        name=body.name,
        start_date=start,
        end_date=end,
        discount_pct=body.discount_pct,
        notes=body.notes,
    )
    db.add(promo)
    await db.flush()
    invalidate_forecast_cache(ctx.workspace_id)
    return {"id": promo.id, "name": promo.name}


@router.put("/{promo_id}")
async def update_promotion(
    promo_id: int,
    body: PromotionUpdate,
    ctx: Ctx = Depends(get_ctx),
    db: AsyncSession = Depends(get_db),
):
    promo = (await db.execute(
        select(PromotionalPeriod).where(
            PromotionalPeriod.id == promo_id,
            PromotionalPeriod.workspace_id == ctx.workspace_id,
        )
    )).scalar_one_or_none()
    if not promo:
        raise HTTPException(status_code=404, detail="Promotion not found.")
    data = body.model_dump(exclude_unset=True)
    start = data.get("start_date", promo.start_date)
    end = data.get("end_date", promo.end_date)
    start, end = _as_pair(start, end)
    promo.start_date = start
    promo.end_date = end
    if "name" in data:
        promo.name = data["name"]
    if "discount_pct" in data:
        promo.discount_pct = data["discount_pct"]
    if "notes" in data:
        promo.notes = data["notes"]
    invalidate_forecast_cache(ctx.workspace_id)
    return {"id": promo.id, "name": promo.name}


@router.delete("/{promo_id}")
async def delete_promotion(
    promo_id: int,
    ctx: Ctx = Depends(get_ctx),
    db: AsyncSession = Depends(get_db),
):
    promo = (await db.execute(
        select(PromotionalPeriod).where(
            PromotionalPeriod.id == promo_id,
            PromotionalPeriod.workspace_id == ctx.workspace_id,
        )
    )).scalar_one_or_none()
    if not promo:
        raise HTTPException(status_code=404, detail="Promotion not found.")
    await db.delete(promo)
    invalidate_forecast_cache(ctx.workspace_id)
    return {"deleted": True}
