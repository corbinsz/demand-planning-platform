import csv
import io
import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.database import async_session
from app.deps import Ctx, get_ctx
from app.services.analytics import (
    abc_summary,
    compute_abc_classification,
    dead_stock_report,
    excess_stock_report,
)
from app.services.audit import write_audit

logger = logging.getLogger(__name__)
router = APIRouter()


def _csv_response(buf: io.StringIO, filename: str) -> StreamingResponse:
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _note_export(ctx: Ctx, name: str) -> None:
    async with async_session() as session:
        await write_audit(
            session,
            workspace_id=ctx.workspace_id,
            actor_email=ctx.actor,
            action="data_export",
            resource=name,
            ip=ctx.ip,
        )
        await session.commit()


@router.get("/abc")
async def get_abc_classification(
    days: int = Query(90, ge=7, le=365),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    ctx: Ctx = Depends(get_ctx),
):
    try:
        data = await abc_summary(ctx.workspace_id, days=days)
    except Exception:
        logger.exception("ABC classification failed")
        raise HTTPException(status_code=500, detail="We couldn't classify the catalog.")
    items = data["items"]
    total = len(items)
    start = (page - 1) * per_page
    return {
        "summary": data["summary"],
        "total_skus": data["total_skus"],
        "items": [asdict(i) for i in items[start:start + per_page]],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page else 0,
    }


@router.get("/dead-stock")
async def get_dead_stock(
    no_sale_days: int = Query(60, ge=14, le=365),
    min_stock: int = Query(1, ge=1),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    ctx: Ctx = Depends(get_ctx),
):
    try:
        items = await dead_stock_report(ctx.workspace_id, no_sale_days=no_sale_days, min_stock=min_stock)
    except Exception:
        logger.exception("Dead stock report failed")
        raise HTTPException(status_code=500, detail="We couldn't build the dead stock report.")
    total = len(items)
    start = (page - 1) * per_page
    return {
        "items": [asdict(i) for i in items[start:start + per_page]],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page else 0,
        "total_value": round(sum(i.inventory_value for i in items), 2),
        "total_units": sum(i.current_stock for i in items),
    }


@router.get("/excess-stock")
async def get_excess_stock(
    target_days: int = Query(90, ge=30, le=365),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    ctx: Ctx = Depends(get_ctx),
):
    try:
        items = await excess_stock_report(ctx.workspace_id, target_days_of_stock=target_days)
    except Exception:
        logger.exception("Excess stock report failed")
        raise HTTPException(status_code=500, detail="We couldn't build the excess stock report.")
    total = len(items)
    start = (page - 1) * per_page
    return {
        "items": [asdict(i) for i in items[start:start + per_page]],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if per_page else 0,
        "total_excess_value": round(sum(i.excess_value for i in items), 2),
        "total_excess_units": sum(i.excess_units for i in items),
    }


@router.get("/abc/export")
async def export_abc_csv(days: int = Query(90, ge=7, le=365), ctx: Ctx = Depends(get_ctx)):
    items = await compute_abc_classification(ctx.workspace_id, days=days)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["SKU", "Title", "Class", "Revenue", "Units Sold", "% of Revenue", "Cumulative %", "Stock", "Days of Stock", "Velocity/day"])
    for i in items:
        writer.writerow([i.sku, i.title, i.abc_class, i.total_revenue, i.total_units, i.pct_of_revenue, i.cumulative_pct, i.current_stock, i.days_of_stock or "", i.daily_velocity])
    await _note_export(ctx, "abc")
    return _csv_response(buf, "abc-classification.csv")


@router.get("/dead-stock/export")
async def export_dead_stock_csv(
    no_sale_days: int = Query(60, ge=14, le=365),
    min_stock: int = Query(1, ge=1),
    ctx: Ctx = Depends(get_ctx),
):
    items = await dead_stock_report(ctx.workspace_id, no_sale_days=no_sale_days, min_stock=min_stock)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["SKU", "Title", "Class", "Stock", "Value at cost", "Last Sold", "Days Silent", "Units (90d)", "Velocity/day", "Recommendation"])
    for i in items:
        writer.writerow([i.sku, i.title, i.abc_class, i.current_stock, i.inventory_value, i.last_sold_date or "Never", i.days_since_last_sale if i.days_since_last_sale is not None else "Never", i.total_units_sold_90d, i.daily_velocity, i.recommendation])
    await _note_export(ctx, "dead-stock")
    return _csv_response(buf, "dead-stock.csv")


@router.get("/excess-stock/export")
async def export_excess_stock_csv(
    target_days: int = Query(90, ge=30, le=365),
    ctx: Ctx = Depends(get_ctx),
):
    items = await excess_stock_report(ctx.workspace_id, target_days_of_stock=target_days)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["SKU", "Title", "Class", "Stock", "Velocity/day", "Days of Stock", "Target Days", "Excess Units", "Excess Value at cost", "Recommendation"])
    for i in items:
        writer.writerow([i.sku, i.title, i.abc_class, i.current_stock, i.daily_velocity, i.days_of_stock, i.target_days, i.excess_units, i.excess_value, i.recommendation])
    await _note_export(ctx, "excess-stock")
    return _csv_response(buf, "excess-stock.csv")
