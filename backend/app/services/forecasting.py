"""Load daily sales for one workspace and run the forecast portfolio."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import timedelta

import numpy as np
import pandas as pd
from sqlalchemy import and_, func, select

from app.database import async_session
from app.models.models import Order, OrderLineItem, Product, PromotionalPeriod, ReorderRule
from app.services.forecast_engine import SkuForecast, promo_uplift_factor, run_portfolio
from app.services.reorder import compute_reorder
from app.services.stock import summed_stock
from app.sqlutil import day_key
from app.timeutil import utcnow_naive

logger = logging.getLogger(__name__)

CACHE_TTL_MINUTES = 30
_cache: dict[int, dict] = {}
_inflight: dict[int, asyncio.Task] = {}
_lock = asyncio.Lock()


@dataclass
class SKUForecast:
    sku: str
    title: str
    avg_daily_velocity_30d: float
    avg_daily_velocity_90d: float
    avg_daily_velocity_365d: float
    rolling_30d_avg: float
    forecast_30d: float
    forecast_60d: float
    forecast_90d: float
    confidence_low_30: float
    confidence_high_30: float
    confidence_low_90: float
    confidence_high_90: float
    has_seasonality: bool
    intermittent: bool
    model: str
    model_mase: float | None
    selection: str
    reorder_point: int
    current_stock: int
    below_reorder_point: bool
    suggested_reorder_qty: int
    days_of_stock_remaining: float | None
    lead_time_days: int
    safety_stock: int


def invalidate_forecast_cache(workspace_id: int | None = None) -> None:
    if workspace_id is None:
        _cache.clear()
    else:
        _cache.pop(workspace_id, None)


def _velocity(values: np.ndarray, days: int) -> float:
    if len(values) == 0:
        return 0.0
    window = values[-days:] if len(values) >= days else values
    return round(float(np.mean(window)), 2)


async def _load_inputs(workspace_id: int):
    now = utcnow_naive()
    cutoff = now - timedelta(days=370)
    async with async_session() as session:
        day = day_key(Order.created_at)
        result = await session.execute(
            select(
                OrderLineItem.sku,
                day.label("sale_date"),
                func.sum(OrderLineItem.quantity).label("qty"),
            )
            .join(
                Order,
                and_(
                    Order.workspace_id == OrderLineItem.workspace_id,
                    Order.order_id == OrderLineItem.order_id,
                ),
            )
            .where(
                OrderLineItem.workspace_id == workspace_id,
                Order.created_at >= cutoff,
            )
            .group_by(OrderLineItem.sku, day)
        )
        rows = result.all()
        titles_result = await session.execute(
            select(Product.sku, Product.title, Product.parent_sku).where(Product.workspace_id == workspace_id)
        )
        titles = {}
        parents = {}
        for sku, title, parent in titles_result.all():
            titles[sku] = title or "Unknown"
            if parent:
                parents[sku] = parent
        rules_result = await session.execute(
            select(ReorderRule).where(ReorderRule.workspace_id == workspace_id)
        )
        rules = {rule.sku: rule for rule in rules_result.scalars().all()}
        stock = await summed_stock(session, workspace_id, "shiphero")
        promos_result = await session.execute(
            select(PromotionalPeriod).where(PromotionalPeriod.workspace_id == workspace_id)
        )
        promos = list(promos_result.scalars().all())

    grouped: dict[str, list] = defaultdict(list)
    for sku, sale_date, qty in rows:
        grouped[sku].append((pd.to_datetime(sale_date), float(qty or 0)))

    end = pd.Timestamp(now.date())
    index = pd.date_range(end=end, periods=365, freq="D")
    future_index = pd.date_range(start=end + pd.Timedelta(days=1), periods=90, freq="D")
    series: dict[str, np.ndarray] = {}
    for sku, points in grouped.items():
        frame = pd.DataFrame(points, columns=["date", "quantity"]).groupby("date", as_index=True).sum()
        aligned = frame.reindex(index, fill_value=0.0)["quantity"].to_numpy(dtype=float)
        series[sku] = aligned

    def uplift_for(dates: pd.DatetimeIndex) -> np.ndarray:
        factors = np.ones(len(dates))
        for promo in promos:
            start = pd.Timestamp(promo.start_date).normalize()
            stop = pd.Timestamp(promo.end_date).normalize()
            factor = promo_uplift_factor(float(promo.discount_pct or 0))
            mask = (dates >= start) & (dates <= stop)
            factors[mask] = np.maximum(factors[mask], factor)
        return factors

    # The same calendar applies to every SKU. Promotions in this app are
    # store-wide, which matches how the seeder and the promotions screen work.
    history_uplift = uplift_for(index)
    future = uplift_for(future_index)
    uplift = {sku: history_uplift.copy() for sku in series}
    future_uplift = {sku: future.copy() for sku in series}
    return series, titles, rules, stock, int(index[0].dayofweek), uplift, future_uplift, parents


def _to_row(sku: str, title: str, fc: SkuForecast, rule, stock_row: dict | None) -> SKUForecast:
    current = int((stock_row or {}).get("available") or 0)
    current = max(current, 0)
    lead = rule.lead_time_days if rule else 14
    safety = rule.safety_stock if rule else 0
    moq = rule.reorder_quantity if rule else None
    manual_point = rule.reorder_point if rule else None
    p30, lo30, hi30 = fc.sum_between(0, 30)
    p60, _, _ = fc.sum_between(0, 60)
    p90, lo90, hi90 = fc.sum_between(0, 90)
    daily_model = p30 / 30.0 if p30 > 0 else 0.0
    plan = compute_reorder(
        daily_demand=daily_model,
        current_stock=current,
        lead_time_days=lead,
        safety_stock=safety,
        moq=moq,
        manual_reorder_point=manual_point,
    )
    return SKUForecast(
        sku=sku,
        title=title,
        avg_daily_velocity_30d=0.0,
        avg_daily_velocity_90d=0.0,
        avg_daily_velocity_365d=0.0,
        rolling_30d_avg=round(daily_model, 2),
        forecast_30d=round(p30, 0),
        forecast_60d=round(p60, 0),
        forecast_90d=round(p90, 0),
        confidence_low_30=round(lo30, 0),
        confidence_high_30=round(hi30, 0),
        confidence_low_90=round(lo90, 0),
        confidence_high_90=round(hi90, 0),
        has_seasonality=fc.has_seasonality,
        intermittent=fc.intermittent,
        model=fc.model,
        model_mase=round(fc.mase, 3) if fc.mase < 100 else None,
        selection=fc.selection,
        reorder_point=plan["reorder_point"],
        current_stock=current,
        below_reorder_point=plan["below_reorder_point"],
        suggested_reorder_qty=plan["suggested_reorder_qty"],
        days_of_stock_remaining=plan["days_of_stock_remaining"],
        lead_time_days=lead,
        safety_stock=safety,
    )


async def _build(workspace_id: int) -> tuple[list[SKUForecast], dict]:
    series, titles, rules, stock, start_dow, uplift, future, parents = await _load_inputs(workspace_id)
    if not series:
        report = {
            "global_winner": None,
            "baseline_ets_mase": None,
            "selected_mase": None,
            "sku_count": 0,
            "per_sku_wins": 0,
            "global_wins": 0,
        }
        return [], report

    def _run():
        return run_portfolio(
            series,
            start_dow=start_dow,
            uplift=uplift,
            future_uplift=future,
            parents=parents,
        )

    portfolio = await asyncio.to_thread(_run)
    rows = []
    for sku, fc in portfolio.skus.items():
        history = series[sku]
        row = _to_row(sku, titles.get(sku, "Unknown"), fc, rules.get(sku), stock.get(sku))
        row.avg_daily_velocity_30d = _velocity(history, 30)
        row.avg_daily_velocity_90d = _velocity(history, 90)
        row.avg_daily_velocity_365d = _velocity(history, 365)
        row.rolling_30d_avg = row.avg_daily_velocity_30d
        rows.append(row)
    rows.sort(key=lambda r: r.sku)
    report = portfolio.report()
    logger.info(
        "Forecasts for workspace %s: %s SKUs, baseline ETS MASE %s, selected MASE %s, winner %s",
        workspace_id,
        len(rows),
        report.get("baseline_ets_mase"),
        report.get("selected_mase"),
        report.get("global_winner"),
    )
    return rows, report


async def generate_all_forecasts(workspace_id: int) -> tuple[list[SKUForecast], dict]:
    now = utcnow_naive()
    cached = _cache.get(workspace_id)
    if cached and cached["expires"] > now:
        return cached["rows"], cached["report"]

    async with _lock:
        cached = _cache.get(workspace_id)
        if cached and cached["expires"] > utcnow_naive():
            return cached["rows"], cached["report"]
        task = _inflight.get(workspace_id)
        if task is None or task.done():
            task = asyncio.create_task(_build(workspace_id))
            _inflight[workspace_id] = task
    try:
        rows, report = await task
    finally:
        if _inflight.get(workspace_id) is task and task.done():
            _inflight.pop(workspace_id, None)
    _cache[workspace_id] = {
        "rows": rows,
        "report": report,
        "expires": utcnow_naive() + timedelta(minutes=CACHE_TTL_MINUTES),
    }
    return rows, report


async def get_reorder_alerts(workspace_id: int) -> list[SKUForecast]:
    rows, _ = await generate_all_forecasts(workspace_id)
    return [row for row in rows if row.below_reorder_point]


def forecast_to_dict(row: SKUForecast) -> dict:
    return asdict(row)


async def update_reorder_points(workspace_id: int) -> int:
    """Refresh stored reorder points from the latest forecast.

    Does not touch reorder_quantity. That column is the supplier minimum
    the buyer set, not a forecast output.
    """
    from app.database import get_upsert

    rows, _ = await generate_all_forecasts(workspace_id)
    upsert = get_upsert()
    async with async_session() as session:
        existing = await session.execute(
            select(ReorderRule.sku).where(ReorderRule.workspace_id == workspace_id)
        )
        known = {sku for (sku,) in existing.all()}
        updated = 0
        for row in rows:
            if row.sku not in known:
                continue
            stmt = (
                upsert(ReorderRule)
                .values(
                    workspace_id=workspace_id,
                    sku=row.sku,
                    reorder_point=row.reorder_point,
                    reorder_quantity=1,
                    lead_time_days=row.lead_time_days,
                    safety_stock=row.safety_stock,
                )
                .on_conflict_do_update(
                    index_elements=["workspace_id", "sku"],
                    set_={"reorder_point": row.reorder_point},
                )
            )
            await session.execute(stmt)
            updated += 1
        await session.commit()
    return updated
