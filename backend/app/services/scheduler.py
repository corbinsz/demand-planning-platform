import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.database import async_session
from app.models.models import JobLog

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _log_job(job_name: str, status: str, started: datetime, error: str | None = None, count: int | None = None):
    """Log job run to database."""
    async with async_session() as session:
        log = JobLog(
            job_name=job_name,
            status=status,
            started_at=started,
            finished_at=datetime.now(timezone.utc),
            error_message=error,
            records_processed=count,
        )
        session.add(log)
        await session.commit()


async def shopify_full_sync_job():
    """Nightly full Shopify sync."""
    started = datetime.now(timezone.utc)
    try:
        from app.services.shopify_sync import full_sync
        result = await full_sync()
        total = sum(result.values())
        await _log_job("shopify_full_sync", "success", started, count=total)
        logger.info(f"Shopify full sync completed: {result}")
    except Exception as e:
        logger.error(f"Shopify full sync failed: {e}")
        await _log_job("shopify_full_sync", "failed", started, error=str(e))


async def shiphero_sync_job():
    """ShipHero inventory sync every 4 hours."""
    started = datetime.now(timezone.utc)
    try:
        from app.services.shiphero_sync import full_sync
        result = await full_sync()
        total = result.get("inventory_synced", 0)
        await _log_job("shiphero_sync", "success", started, count=total)
        logger.info(f"ShipHero sync completed: {result}")
    except Exception as e:
        logger.error(f"ShipHero sync failed: {e}")
        await _log_job("shiphero_sync", "failed", started, error=str(e))


async def forecasting_job():
    """Nightly forecast recalculation + reorder rule update."""
    started = datetime.now(timezone.utc)
    try:
        from app.services.forecasting import update_reorder_rules
        count = await update_reorder_rules()
        await _log_job("forecasting", "success", started, count=count)
        logger.info(f"Forecasting completed for {count} SKUs")
    except Exception as e:
        logger.error(f"Forecasting failed: {e}")
        await _log_job("forecasting", "failed", started, error=str(e))


async def reconciliation_job():
    """Reconciliation every 4 hours."""
    started = datetime.now(timezone.utc)
    try:
        from app.services.reconciliation import reconcile_inventory
        records = await reconcile_inventory()
        await _log_job("reconciliation", "success", started, count=len(records))
        logger.info(f"Reconciliation completed for {len(records)} SKUs")
    except Exception as e:
        logger.error(f"Reconciliation failed: {e}")
        await _log_job("reconciliation", "failed", started, error=str(e))


def start_scheduler():
    """Configure and start the APScheduler."""
    # Shopify full sync — nightly at 2am UTC
    scheduler.add_job(
        shopify_full_sync_job,
        trigger=CronTrigger(hour=2, minute=0),
        id="shopify_full_sync",
        name="Shopify Full Sync",
        replace_existing=True,
    )

    # ShipHero sync — every 4 hours
    scheduler.add_job(
        shiphero_sync_job,
        trigger=IntervalTrigger(hours=4),
        id="shiphero_sync",
        name="ShipHero Sync",
        replace_existing=True,
    )

    # Forecasting — nightly at 3am UTC
    scheduler.add_job(
        forecasting_job,
        trigger=CronTrigger(hour=3, minute=0),
        id="forecasting",
        name="Forecast Recalculation",
        replace_existing=True,
    )

    # Reconciliation — every 4 hours, offset by 30 min from ShipHero sync
    recon_start = datetime.now(timezone.utc) + timedelta(minutes=30)
    scheduler.add_job(
        reconciliation_job,
        trigger=IntervalTrigger(hours=4, start_date=recon_start),
        id="reconciliation",
        name="Inventory Reconciliation",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started with 4 jobs configured")


def shutdown_scheduler():
    """Gracefully shut down the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")
