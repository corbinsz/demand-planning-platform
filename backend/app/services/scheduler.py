"""Scheduled jobs.

Nothing calls Shopify or ShipHero on boot. Interval-style work uses cron
so a restart does not immediately hit a vendor API. The weekly note is
Monday 8:00am Mountain Time (Utah), which is 15:00 UTC in standard time.
"""

import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.config import get_settings
from app.database import async_session
from app.models.models import JobLog, Workspace
from app.services.credentials import get_shiphero_auth, get_shopify_auth
from app.timeutil import utcnow_naive

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _log_job(workspace_id: int | None, job_name: str, status: str, started: datetime, error: str | None = None, count: int | None = None):
    async with async_session() as session:
        session.add(JobLog(
            workspace_id=workspace_id,
            job_name=job_name,
            status=status,
            started_at=started,
            finished_at=utcnow_naive(),
            error_message=(error or "")[:500] or None,
            records_processed=count,
        ))
        await session.commit()


async def _workspace_ids() -> list[int]:
    async with async_session() as session:
        rows = await session.execute(select(Workspace.id))
        return [row[0] for row in rows.all()]


async def shopify_full_sync_job():
    from app.services.shopify_sync import full_sync
    for workspace_id in await _workspace_ids():
        started = utcnow_naive()
        async with async_session() as session:
            auth = await get_shopify_auth(session, workspace_id)
        if auth is None:
            continue
        try:
            result = await full_sync(workspace_id, auth.domain, auth.token)
            await _log_job(workspace_id, "shopify_full_sync", "success", started, count=sum(result.values()))
        except Exception:
            logger.exception("Shopify sync failed for workspace %s", workspace_id)
            await _log_job(workspace_id, "shopify_full_sync", "failed", started, error="Sync failed")


async def shiphero_sync_job():
    from app.services.shiphero_sync import full_sync
    for workspace_id in await _workspace_ids():
        started = utcnow_naive()
        async with async_session() as session:
            auth = await get_shiphero_auth(session, workspace_id)
        if auth is None:
            continue
        try:
            result = await full_sync(workspace_id, auth.access_token)
            await _log_job(workspace_id, "shiphero_sync", "success", started, count=result.get("inventory_synced", 0))
        except Exception:
            logger.exception("ShipHero sync failed for workspace %s", workspace_id)
            await _log_job(workspace_id, "shiphero_sync", "failed", started, error="Sync failed")


async def forecasting_job():
    from app.services.forecasting import invalidate_forecast_cache, update_reorder_points
    for workspace_id in await _workspace_ids():
        started = utcnow_naive()
        try:
            invalidate_forecast_cache(workspace_id)
            count = await update_reorder_points(workspace_id)
            await _log_job(workspace_id, "forecasting", "success", started, count=count)
        except Exception:
            logger.exception("Forecasting failed for workspace %s", workspace_id)
            await _log_job(workspace_id, "forecasting", "failed", started, error="Forecast failed")


async def reconciliation_job():
    from app.services.reconciliation import reconcile_inventory
    for workspace_id in await _workspace_ids():
        started = utcnow_naive()
        try:
            records = await reconcile_inventory(workspace_id)
            await _log_job(workspace_id, "reconciliation", "success", started, count=len(records))
        except Exception:
            logger.exception("Reconciliation failed for workspace %s", workspace_id)
            await _log_job(workspace_id, "reconciliation", "failed", started, error="Reconciliation failed")


async def weekly_digest_job():
    from app.services.alerts import dispatch_weekly_digest
    for workspace_id in await _workspace_ids():
        try:
            await dispatch_weekly_digest(workspace_id)
        except Exception:
            logger.exception("Weekly digest failed for workspace %s", workspace_id)


def start_scheduler():
    settings = get_settings()
    if not settings.scheduler_enabled:
        logger.info("Scheduler disabled")
        return
    if scheduler.running:
        return
    scheduler.add_job(shopify_full_sync_job, CronTrigger(hour=2, minute=0), id="shopify_full_sync", replace_existing=True)
    scheduler.add_job(shiphero_sync_job, CronTrigger(hour="1,5,9,13,17,21", minute=15), id="shiphero_sync", replace_existing=True)
    scheduler.add_job(forecasting_job, CronTrigger(hour=3, minute=10), id="forecasting", replace_existing=True)
    scheduler.add_job(reconciliation_job, CronTrigger(hour="2,6,10,14,18,22", minute=40), id="reconciliation", replace_existing=True)
    # Monday 15:00 UTC = 8:00am Mountain Standard Time (Utah).
    scheduler.add_job(weekly_digest_job, CronTrigger(day_of_week="mon", hour=15, minute=0), id="weekly_digest", replace_existing=True)
    scheduler.start()
    logger.info("Scheduler started (no jobs run at boot)")


def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")
