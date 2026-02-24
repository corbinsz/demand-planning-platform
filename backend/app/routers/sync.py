import logging
import time
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.models import JobLog

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()

# Track running sync status in memory
_SYNC_TIMEOUT = 600  # 10 minutes max before considering a sync stuck
_sync_status = {
    "shopify": {"running": False, "last_result": None, "started_at": 0},
    "shiphero": {"running": False, "last_result": None, "started_at": 0},
}


def _is_stuck(source: str) -> bool:
    """Check if a sync has been running longer than timeout."""
    s = _sync_status[source]
    if s["running"] and s["started_at"] > 0:
        return (time.time() - s["started_at"]) > _SYNC_TIMEOUT
    return False


@router.get("/status")
async def sync_status(db: AsyncSession = Depends(get_db)):
    """Get last sync times and status for all sources."""
    # Last successful job per type
    jobs = {}
    for job_name in ["shopify_full_sync", "shiphero_sync", "forecasting", "reconciliation"]:
        result = await db.execute(
            select(JobLog)
            .where(JobLog.job_name == job_name)
            .order_by(JobLog.started_at.desc())
            .limit(1)
        )
        job = result.scalar_one_or_none()
        if job:
            jobs[job_name] = {
                "status": job.status,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                "records_processed": job.records_processed,
                "error": job.error_message,
            }
        else:
            jobs[job_name] = {"status": "never_run", "started_at": None, "finished_at": None, "records_processed": None, "error": None}

    return {
        "jobs": jobs,
        "shopify_running": _sync_status["shopify"]["running"],
        "shiphero_running": _sync_status["shiphero"]["running"],
    }


@router.post("/test-shopify")
async def test_shopify_connection():
    """Test Shopify API connection with current credentials."""
    url = f"https://{settings.shopify_store_domain}/admin/api/2024-01/shop.json"
    headers = {
        "X-Shopify-Access-Token": settings.shopify_access_token,
        "Content-Type": "application/json",
    }

    if settings.shopify_access_token == "shpat_placeholder":
        return {"success": False, "error": "Shopify access token is still set to placeholder. Update SHOPIFY_ACCESS_TOKEN in backend/.env"}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                shop = resp.json().get("shop", {})
                return {
                    "success": True,
                    "store_name": shop.get("name"),
                    "domain": shop.get("myshopify_domain"),
                    "plan": shop.get("plan_display_name"),
                    "currency": shop.get("currency"),
                }
            elif resp.status_code == 401:
                return {"success": False, "error": "Invalid access token. Check SHOPIFY_ACCESS_TOKEN in .env"}
            elif resp.status_code == 404:
                return {"success": False, "error": f"Store not found: {settings.shopify_store_domain}. Check SHOPIFY_STORE_DOMAIN in .env"}
            else:
                return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except httpx.ConnectError:
        return {"success": False, "error": f"Cannot connect to {settings.shopify_store_domain}. Check the domain."}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/test-shiphero")
async def test_shiphero_connection():
    """Test ShipHero API connection with current credentials."""
    if settings.shiphero_api_token == "placeholder_token":
        return {"success": False, "error": "ShipHero API token is still set to placeholder. Update SHIPHERO_API_TOKEN in backend/.env"}

    query = '{ account { id legacy_id } }'
    headers = {
        "Authorization": f"Bearer {settings.shiphero_api_token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://public-api.shiphero.com/graphql",
                headers=headers,
                json={"query": query},
            )
            if resp.status_code == 200:
                data = resp.json()
                if "errors" in data:
                    return {"success": False, "error": data["errors"][0].get("message", "Unknown GraphQL error")}
                account = data.get("data", {}).get("account", {})
                return {
                    "success": True,
                    "account_id": account.get("id"),
                    "legacy_id": account.get("legacy_id"),
                }
            elif resp.status_code == 401:
                return {"success": False, "error": "Invalid API token. Check SHIPHERO_API_TOKEN in .env"}
            else:
                return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except httpx.ConnectError:
        return {"success": False, "error": "Cannot connect to ShipHero API."}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _run_shopify_sync():
    """Background task for Shopify sync."""
    _sync_status["shopify"]["running"] = True
    _sync_status["shopify"]["started_at"] = time.time()
    try:
        from app.services.shopify_sync import full_sync
        result = await full_sync()
        _sync_status["shopify"]["last_result"] = {"success": True, **result}
    except Exception as e:
        logger.exception("Shopify sync failed")
        _sync_status["shopify"]["last_result"] = {"success": False, "error": str(e)}
    finally:
        _sync_status["shopify"]["running"] = False
        _sync_status["shopify"]["started_at"] = 0


async def _run_shiphero_sync():
    """Background task for ShipHero sync."""
    _sync_status["shiphero"]["running"] = True
    _sync_status["shiphero"]["started_at"] = time.time()
    try:
        from app.services.shiphero_sync import full_sync
        result = await full_sync()
        _sync_status["shiphero"]["last_result"] = {"success": True, **result}
    except Exception as e:
        logger.exception("ShipHero sync failed")
        _sync_status["shiphero"]["last_result"] = {"success": False, "error": str(e)}
    finally:
        _sync_status["shiphero"]["running"] = False
        _sync_status["shiphero"]["started_at"] = 0


@router.post("/trigger/shopify")
async def trigger_shopify_sync(background_tasks: BackgroundTasks):
    """Trigger a manual Shopify full sync."""
    if _sync_status["shopify"]["running"] and not _is_stuck("shopify"):
        return {"started": False, "message": "Shopify sync is already running"}
    if _is_stuck("shopify"):
        logger.warning("Shopify sync was stuck, resetting state")
        _sync_status["shopify"]["running"] = False
    background_tasks.add_task(_run_shopify_sync)
    return {"started": True, "message": "Shopify sync started"}


@router.post("/trigger/shiphero")
async def trigger_shiphero_sync(background_tasks: BackgroundTasks):
    """Trigger a manual ShipHero sync."""
    if _sync_status["shiphero"]["running"] and not _is_stuck("shiphero"):
        return {"started": False, "message": "ShipHero sync is already running"}
    if _is_stuck("shiphero"):
        logger.warning("ShipHero sync was stuck, resetting state")
        _sync_status["shiphero"]["running"] = False
    background_tasks.add_task(_run_shiphero_sync)
    return {"started": True, "message": "ShipHero sync started"}
