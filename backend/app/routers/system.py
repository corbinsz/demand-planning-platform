"""Today's decisions, alerts, the weekly email preview, and client error reports."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import Ctx, get_ctx
from app.models.models import AuditLog
from app.services.alerts import dispatch_weekly_digest, render_weekly_email, today_payload

logger = logging.getLogger(__name__)
router = APIRouter()


class ClientErrorIn(BaseModel):
    message: str = Field(max_length=300)
    path: str | None = Field(default=None, max_length=200)


@router.get("/today")
async def today(ctx: Ctx = Depends(get_ctx)):
    try:
        return await today_payload(ctx.workspace_id)
    except Exception:
        logger.exception("Today payload failed")
        raise HTTPException(status_code=500, detail="We couldn't prepare today's list.")


@router.get("/alerts")
async def alerts(ctx: Ctx = Depends(get_ctx)):
    payload = await today_payload(ctx.workspace_id)
    return {"items": payload["alerts"], "total": len(payload["alerts"])}


@router.get("/digest")
async def digest_preview(ctx: Ctx = Depends(get_ctx)):
    payload = await today_payload(ctx.workspace_id)
    email = render_weekly_email(payload)
    return {
        "schedule": "Mondays at 8:00am Mountain Time (Utah)",
        "delivery": "Preview only until SMTP or a webhook is configured.",
        **email,
    }


@router.post("/digest/send")
async def digest_send(ctx: Ctx = Depends(get_ctx)):
    """Send only if the server owner configured a channel. Otherwise return the preview."""
    try:
        result = await dispatch_weekly_digest(ctx.workspace_id)
    except Exception:
        logger.exception("Digest dispatch failed")
        raise HTTPException(status_code=500, detail="We couldn't prepare the weekly email.")
    return result


@router.get("/audit")
async def audit_list(ctx: Ctx = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(AuditLog)
        .where(AuditLog.workspace_id == ctx.workspace_id)
        .order_by(AuditLog.created_at.desc())
        .limit(50)
    )).scalars().all()
    return {
        "items": [
            {
                "id": row.id,
                "action": row.action,
                "actor": row.actor_email,
                "resource": row.resource,
                "detail": row.detail,
                "at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
    }


@router.post("/client-errors")
async def client_errors(body: ClientErrorIn, request: Request):
    """First-party error hook. The message is truncated and not tied to a person."""
    path = (body.path or request.url.path)[:200]
    logger.warning("client_error path=%s message=%s", path, body.message[:300])
    return {"ok": True}
