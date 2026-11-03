"""Client brief, PDF, and expiring read-only share links."""

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import async_session, get_db
from app.deps import Ctx, get_ctx
from app.models.models import ShareLink
from app.services.audit import write_audit
from app.services.reporting import build_brief, render_brief_pdf
from app.timeutil import utcnow_naive

router = APIRouter()


@router.get("/brief")
async def brief(ctx: Ctx = Depends(get_ctx)):
    try:
        return await build_brief(ctx.workspace_id)
    except Exception:
        raise HTTPException(status_code=500, detail="We couldn't build the brief.")


@router.get("/brief.pdf")
async def brief_pdf(ctx: Ctx = Depends(get_ctx)):
    try:
        payload = await build_brief(ctx.workspace_id)
        pdf = render_brief_pdf(payload)
    except Exception:
        raise HTTPException(status_code=500, detail="We couldn't build the PDF.")
    async with async_session() as session:
        await write_audit(
            session, workspace_id=ctx.workspace_id, actor_email=ctx.actor,
            action="data_export", resource="brief.pdf", ip=ctx.ip,
        )
        await session.commit()
    filename = "inventory-brief.pdf"
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
    })


@router.post("/share")
async def create_share(ctx: Ctx = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    if ctx.user is None and not ctx.workspace.is_demo:
        raise HTTPException(status_code=401, detail="Sign in to create a share link.")
    token = secrets.token_urlsafe(32)
    expires = utcnow_naive() + timedelta(days=14)
    db.add(ShareLink(
        workspace_id=ctx.workspace_id,
        token=token,
        label="Inventory brief",
        expires_at=expires,
        created_by=ctx.actor,
    ))
    await write_audit(
        db, workspace_id=ctx.workspace_id, actor_email=ctx.actor,
        action="share_create", resource="brief", ip=ctx.ip,
    )
    settings = get_settings()
    return {
        "token": token,
        "url": settings.frontend_url.rstrip("/") + f"/share/{token}",
        "expires_at": expires.isoformat() + "Z",
    }


async def _live_link(db: AsyncSession, token: str) -> ShareLink:
    link = (await db.execute(select(ShareLink).where(ShareLink.token == token))).scalar_one_or_none()
    if link is None or link.revoked or link.expires_at < utcnow_naive():
        raise HTTPException(status_code=404, detail="This link is no longer available.")
    return link


@router.get("/share/{token}")
async def shared_brief(token: str, db: AsyncSession = Depends(get_db)):
    link = await _live_link(db, token)
    try:
        payload = await build_brief(link.workspace_id)
    except Exception:
        raise HTTPException(status_code=500, detail="We couldn't open this brief.")
    payload["shared"] = True
    payload["expires_at"] = link.expires_at.isoformat() + "Z"
    return payload


@router.get("/share/{token}/pdf")
async def shared_pdf(token: str, db: AsyncSession = Depends(get_db)):
    link = await _live_link(db, token)
    try:
        payload = await build_brief(link.workspace_id)
        pdf = render_brief_pdf(payload)
    except Exception:
        raise HTTPException(status_code=500, detail="We couldn't open this brief.")
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": 'inline; filename="inventory-brief.pdf"',
    })
