import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps import Ctx, get_ctx
from app.services.forecasting import forecast_to_dict, generate_all_forecasts, get_reorder_alerts

logger = logging.getLogger(__name__)
router = APIRouter()

FORECAST_SORT_KEYS = {
    "sku", "title", "rolling_30d_avg", "forecast_30d", "forecast_60d",
    "forecast_90d", "current_stock", "days_of_stock_remaining", "model_mase",
}


@router.get("")
async def list_forecasts(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    sort_by: str = Query("sku"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$"),
    ctx: Ctx = Depends(get_ctx),
):
    try:
        rows, report = await generate_all_forecasts(ctx.workspace_id)
    except Exception:
        logger.exception("Forecast generation failed")
        raise HTTPException(status_code=500, detail="We couldn't build forecasts.")

    if sort_by in FORECAST_SORT_KEYS:
        rows = sorted(
            rows,
            key=lambda row: (getattr(row, sort_by, None) is None, getattr(row, sort_by, None) or 0),
            reverse=(sort_dir == "desc"),
        )
    total = len(rows)
    start = (page - 1) * per_page
    page_items = rows[start:start + per_page]
    return {
        "items": [forecast_to_dict(row) for row in page_items],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page else 0,
        "model_report": report,
    }


@router.get("/alerts")
async def reorder_alerts(ctx: Ctx = Depends(get_ctx)):
    try:
        alerts = await get_reorder_alerts(ctx.workspace_id)
    except Exception:
        logger.exception("Reorder alerts failed")
        raise HTTPException(status_code=500, detail="We couldn't load reorder alerts.")
    return {"items": [asdict(row) for row in alerts], "total": len(alerts)}


@router.get("/model-report")
async def model_report(ctx: Ctx = Depends(get_ctx)):
    try:
        _, report = await generate_all_forecasts(ctx.workspace_id)
    except Exception:
        logger.exception("Model report failed")
        raise HTTPException(status_code=500, detail="We couldn't load the model report.")
    return report


@router.get("/{sku}")
async def get_sku_forecast(sku: str, ctx: Ctx = Depends(get_ctx)):
    try:
        rows, _ = await generate_all_forecasts(ctx.workspace_id)
    except Exception:
        logger.exception("Forecast for %s failed", sku)
        raise HTTPException(status_code=500, detail="We couldn't build that forecast.")
    match = next((row for row in rows if row.sku == sku), None)
    if match is None:
        raise HTTPException(status_code=404, detail="No forecast for that SKU.")
    return forecast_to_dict(match)
