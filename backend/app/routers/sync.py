"""Manual sync. Jobs no-op with a clear message until a workspace is connected."""

import logging
import time

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session, get_db
from app.deps import Ctx, get_ctx
from app.models.models import JobLog
from app.services.audit import write_audit
from app.services.credentials import get_shiphero_auth, get_shopify_auth
from app.services.forecasting import invalidate_forecast_cache
from app.timeutil import utcnow_naive

logger = logging.getLogger(__name__)
router = APIRouter()

_SYNC_TIMEOUT = 600
_running: dict[tuple[int, str], float] = {}


def _busy(workspace_id: int, source: str) -> bool:
    started = _running.get((workspace_id, source))
    if not started:
        return False
    if time.time() - started > _SYNC_TIMEOUT:
        _running.pop((workspace_id, source), None)
        return False
    return True


@router.get("/status")
async def sync_status(ctx: Ctx = Depends(get_ctx), db: AsyncSession = Depends(get_db)):
    jobs = {}
    for job_name in ["shopify_full_sync", "shiphero_sync", "forecasting", "reconciliation", "weekly_digest"]:
        job = (await db.execute(
            select(JobLog)
            .where(JobLog.workspace_id == ctx.workspace_id, JobLog.job_name == job_name)
            .order_by(JobLog.started_at.desc())
            .limit(1)
        )).scalar_one_or_none()
        if job:
            jobs[job_name] = {
                "status": job.status,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                "records_processed": job.records_processed,
                "error": job.error_message,
            }
        else:
            jobs[job_name] = {
                "status": "never_run",
                "started_at": None,
                "finished_at": None,
                "records_processed": None,
                "error": None,
            }
    return {
        "jobs": jobs,
        "shopify_running": _busy(ctx.workspace_id, "shopify"),
        "shiphero_running": _busy(ctx.workspace_id, "shiphero"),
    }


async def _run(workspace_id: int, source: str, fn) -> None:
    _running[(workspace_id, source)] = time.time()
    started = utcnow_naive()
    try:
        result = await fn()
        count = sum(v for v in result.values() if isinstance(v, int))
        await _log(workspace_id, f"{source}_full_sync" if source == "shopify" else f"{source}_sync", "success", started, count=count)
        invalidate_forecast_cache(workspace_id)
    except Exception as exc:
        logger.exception("%s sync failed", source)
        await _log(workspace_id, f"{source}_sync", "failed", started, error="Sync failed")
        _ = exc
    finally:
        _running.pop((workspace_id, source), None)


async def _log(workspace_id, name, status, started, count=None, error=None):
    async with async_session() as session:
        session.add(JobLog(
            workspace_id=workspace_id,
            job_name=name,
            status=status,
            started_at=started,
            finished_at=utcnow_naive(),
            records_processed=count,
            error_message=error,
        ))
        await session.commit()


@router.post("/trigger/shopify")
async def trigger_shopify(
    background: BackgroundTasks,
    ctx: Ctx = Depends(get_ctx),
    db: AsyncSession = Depends(get_db),
):
    if ctx.user is None:
        return {
            "started": False,
            "message": "This sample brand uses built-in data. Sign in and connect Shopify to sync a live store.",
        }
    auth = await get_shopify_auth(db, ctx.workspace_id)
    if auth is None:
        return {
            "started": False,
            "message": "Shopify is not connected. The sample brand uses built-in data, so there is nothing to sync.",
        }
    if _busy(ctx.workspace_id, "shopify"):
        return {"started": False, "message": "A Shopify sync is already running."}

    async def job():
        from app.services.shopify_sync import full_sync
        await _run(ctx.workspace_id, "shopify", lambda: full_sync(ctx.workspace_id, auth.domain, auth.token))

    await write_audit(db, workspace_id=ctx.workspace_id, actor_email=ctx.actor, action="sync_start", resource="shopify", ip=ctx.ip)
    background.add_task(job)
    return {"started": True, "message": "Shopify sync started."}


@router.post("/trigger/shiphero")
async def trigger_shiphero(
    background: BackgroundTasks,
    ctx: Ctx = Depends(get_ctx),
    db: AsyncSession = Depends(get_db),
):
    if ctx.user is None:
        return {
            "started": False,
            "message": "This sample brand uses built-in data. Sign in and connect ShipHero to sync a live warehouse.",
        }
    auth = await get_shiphero_auth(db, ctx.workspace_id)
    if auth is None:
        return {
            "started": False,
            "message": "ShipHero is not connected. The sample brand uses built-in data, so there is nothing to sync.",
        }
    if _busy(ctx.workspace_id, "shiphero"):
        return {"started": False, "message": "A ShipHero sync is already running."}

    async def job():
        from app.services.shiphero_sync import full_sync
        await _run(ctx.workspace_id, "shiphero", lambda: full_sync(ctx.workspace_id, auth.access_token))

    await write_audit(db, workspace_id=ctx.workspace_id, actor_email=ctx.actor, action="sync_start", resource="shiphero", ip=ctx.ip)
    background.add_task(job)
    return {"started": True, "message": "ShipHero sync started."}
