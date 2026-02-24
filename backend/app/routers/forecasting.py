import logging
from dataclasses import asdict

from fastapi import APIRouter, Query, HTTPException

from app.database import async_session
from app.services.forecasting import generate_forecast, generate_all_forecasts, get_reorder_alerts

logger = logging.getLogger(__name__)
router = APIRouter()


FORECAST_SORT_KEYS = {
    "sku", "title", "rolling_30d_avg", "forecast_30d", "forecast_60d",
    "forecast_90d", "current_stock", "days_of_stock_remaining",
}


@router.get("")
async def list_forecasts(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    sort_by: str = Query("sku"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
):
    """Get forecasts for all SKUs with pagination and sorting."""
    try:
        all_forecasts = await generate_all_forecasts()
    except Exception as e:
        logger.error(f"Forecast generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate forecasts: {e}")

    # Sort in-memory
    if sort_by in FORECAST_SORT_KEYS:
        all_forecasts.sort(
            key=lambda f: (getattr(f, sort_by, None) is None, getattr(f, sort_by, None) or 0),
            reverse=(sort_dir == "desc"),
        )

    total = len(all_forecasts)
    start = (page - 1) * per_page
    end = start + per_page
    page_items = all_forecasts[start:end]

    return {
        "items": [asdict(f) for f in page_items],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


@router.get("/alerts")
async def reorder_alerts():
    """Get SKUs that are below their reorder point."""
    try:
        alerts = await get_reorder_alerts()
    except Exception as e:
        logger.error(f"Reorder alerts failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load reorder alerts: {e}")
    return {
        "items": [asdict(a) for a in alerts],
        "total": len(alerts),
    }


@router.get("/{sku}")
async def get_sku_forecast(sku: str):
    """Get detailed forecast for a specific SKU."""
    try:
        async with async_session() as session:
            forecast = await generate_forecast(session, sku)
    except Exception as e:
        logger.error(f"Forecast for {sku} failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate forecast for {sku}: {e}")
    if not forecast:
        raise HTTPException(status_code=404, detail=f"No forecast data for SKU: {sku}")
    return asdict(forecast)
