import csv
import io
import logging
from dataclasses import asdict

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import StreamingResponse

from app.services.analytics import (
    compute_abc_classification,
    abc_summary,
    dead_stock_report,
    excess_stock_report,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/abc")
async def get_abc_classification(
    days: int = Query(90, ge=7, le=365, description="Lookback period in days"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """ABC classification based on revenue contribution (Pareto 80/15/5)."""
    try:
        data = await abc_summary(days=days)
    except Exception as e:
        logger.error(f"ABC classification failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to compute ABC classification: {e}")

    all_items = data["items"]
    total = len(all_items)
    start = (page - 1) * per_page
    end = start + per_page

    return {
        "summary": data["summary"],
        "total_skus": data["total_skus"],
        "items": [asdict(i) for i in all_items[start:end]],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


@router.get("/dead-stock")
async def get_dead_stock(
    no_sale_days: int = Query(60, ge=14, le=365, description="Days without sales to consider dead"),
    min_stock: int = Query(1, ge=1, description="Minimum stock to include"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """Dead stock report — SKUs with inventory but no/very low sales."""
    try:
        items = await dead_stock_report(no_sale_days=no_sale_days, min_stock=min_stock)
    except Exception as e:
        logger.error(f"Dead stock report failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to compute dead stock report: {e}")
    total_value = sum(i.inventory_value for i in items)
    total_units = sum(i.current_stock for i in items)

    total = len(items)
    start = (page - 1) * per_page
    end = start + per_page

    return {
        "items": [asdict(i) for i in items[start:end]],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "total_value": round(total_value, 2),
        "total_units": total_units,
    }


@router.get("/excess-stock")
async def get_excess_stock(
    target_days: int = Query(90, ge=30, le=365, description="Target days of stock coverage"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """Excess stock report — SKUs with more inventory than needed."""
    try:
        items = await excess_stock_report(target_days_of_stock=target_days)
    except Exception as e:
        logger.error(f"Excess stock report failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to compute excess stock report: {e}")
    total_excess_value = sum(i.excess_value for i in items)
    total_excess_units = sum(i.excess_units for i in items)

    total = len(items)
    start = (page - 1) * per_page
    end = start + per_page

    return {
        "items": [asdict(i) for i in items[start:end]],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "total_excess_value": round(total_excess_value, 2),
        "total_excess_units": total_excess_units,
    }


# ---------------------------------------------------------------------------
# CSV Export Endpoints
# ---------------------------------------------------------------------------

def _csv_response(buf: io.StringIO, filename: str) -> StreamingResponse:
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/abc/export")
async def export_abc_csv(
    days: int = Query(90, ge=7, le=365),
):
    """Export ABC classification as CSV."""
    items = await compute_abc_classification(days=days)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["SKU", "Title", "Class", "Revenue", "Units Sold", "% of Revenue", "Cumulative %", "Stock", "Days of Stock", "Velocity/day"])
    for i in items:
        writer.writerow([i.sku, i.title, i.abc_class, i.total_revenue, i.total_units, i.pct_of_revenue, i.cumulative_pct, i.current_stock, i.days_of_stock or "", i.daily_velocity])
    return _csv_response(buf, "abc-classification.csv")


@router.get("/dead-stock/export")
async def export_dead_stock_csv(
    no_sale_days: int = Query(60, ge=14, le=365),
    min_stock: int = Query(1, ge=1),
):
    """Export dead stock report as CSV."""
    items = await dead_stock_report(no_sale_days=no_sale_days, min_stock=min_stock)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["SKU", "Title", "Class", "Stock", "Value", "Last Sold", "Days Silent", "Units (90d)", "Velocity/day", "Recommendation"])
    for i in items:
        writer.writerow([i.sku, i.title, i.abc_class, i.current_stock, i.inventory_value, i.last_sold_date or "Never", i.days_since_last_sale or "Never", i.total_units_sold_90d, i.daily_velocity, i.recommendation])
    return _csv_response(buf, "dead-stock.csv")


@router.get("/excess-stock/export")
async def export_excess_stock_csv(
    target_days: int = Query(90, ge=30, le=365),
):
    """Export excess stock report as CSV."""
    items = await excess_stock_report(target_days_of_stock=target_days)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["SKU", "Title", "Class", "Stock", "Velocity/day", "Days of Stock", "Target Days", "Excess Units", "Excess Value", "Recommendation"])
    for i in items:
        writer.writerow([i.sku, i.title, i.abc_class, i.current_stock, i.daily_velocity, i.days_of_stock, i.target_days, i.excess_units, i.excess_value, i.recommendation])
    return _csv_response(buf, "excess-stock.csv")
