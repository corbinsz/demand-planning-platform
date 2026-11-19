"""Per-SKU demand forecasts.

Daily sales are cleaned, checked for a weekly or monthly repeat, and passed
to Holt-Winters exponential smoothing. A short or awkward series falls back
to its recent average so one bad SKU does not fail the page. The model is
fit once per SKU and the 30, 60, and 90 day totals are slices of that
forecast. Results are cached in memory for 30 minutes.
"""

import logging
import warnings
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import and_, func, select
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from app.database import async_session, day_bucket, get_upsert
from app.models.models import Order, OrderLineItem, Product, ReorderRule
from app.services.reorder import compute_reorder_point, suggest_order_quantity
from app.services.stock import position_for_sku, positions_by_sku

logger = logging.getLogger(__name__)

_forecast_cache: dict = {"data": [], "expires": None}
CACHE_TTL_MINUTES = 30
_MIN_HISTORY_DAYS = 14
_SEASONAL_HISTORY_DAYS = 60
_SEASONAL_AUTOCORR = 0.3


@dataclass
class SKUForecast:
    """Forecast and reorder fields for one SKU."""

    sku: str
    title: str
    avg_daily_velocity_30d: float
    avg_daily_velocity_90d: float
    avg_daily_velocity_365d: float
    rolling_30d_avg: float
    forecast_30d: float
    forecast_60d: float
    forecast_90d: float
    has_seasonality: bool
    reorder_point: int
    current_stock: int
    below_reorder_point: bool
    suggested_reorder_qty: int
    days_of_stock_remaining: float | None
    lead_time_days: int
    safety_stock: int


def clear_forecast_cache() -> None:
    """Drop the in-memory forecast cache. Tests call this between cases."""
    _forecast_cache["data"] = []
    _forecast_cache["expires"] = None


def _rows_to_frame(rows: list[tuple]) -> pd.DataFrame:
    """Daily quantity frame with missing days filled as zero sales."""
    if not rows:
        return pd.DataFrame(columns=["date", "quantity"])
    frame = pd.DataFrame(rows, columns=["date", "quantity"])
    frame["date"] = pd.to_datetime(frame["date"])
    date_range = pd.date_range(
        start=frame["date"].min(), end=frame["date"].max(), freq="D"
    )
    frame = frame.set_index("date").reindex(date_range, fill_value=0).reset_index()
    frame.columns = ["date", "quantity"]
    return frame


async def _get_daily_sales(session, sku: str, days: int = 365) -> pd.DataFrame:
    """Daily units sold for one SKU over the last ``days`` days."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    sale_day = day_bucket(Order.created_at)
    result = await session.execute(
        select(
            sale_day.label("sale_date"),
            func.sum(OrderLineItem.quantity).label("total_qty"),
        )
        .join(Order, OrderLineItem.order_id == Order.order_id)
        .where(and_(OrderLineItem.sku == sku, Order.created_at >= cutoff))
        .group_by(sale_day)
        .order_by(sale_day)
    )
    return _rows_to_frame(result.all())


def _remove_outliers(series: pd.Series, z_threshold: float = 3.0) -> pd.Series:
    """Replace days more than ``z_threshold`` standard deviations from the mean.

    A one-off bulk order would otherwise dominate the forecast. Short series
    are left alone because a z-score is not meaningful yet.
    """
    values = series.astype(float)
    if len(values) < 10:
        return values
    std = float(values.std())
    if std == 0:
        return values
    mean = float(values.mean())
    z_scores = np.abs((values - mean) / std)
    cleaned = values.copy()
    cleaned[z_scores > z_threshold] = mean
    return cleaned


def _calculate_velocity(frame: pd.DataFrame, days: int) -> float:
    """Mean daily units over the most recent ``days`` rows."""
    if frame.empty:
        return 0.0
    return round(float(frame.tail(days)["quantity"].mean()), 2)


def _detect_seasonality(frame: pd.DataFrame) -> bool:
    """True when weekly (lag 7) or monthly (lag 30) autocorrelation is strong."""
    if len(frame) < _SEASONAL_HISTORY_DAYS:
        return False
    series = frame["quantity"]
    if float(series.std()) == 0:
        return False
    autocorr_7 = series.autocorr(lag=7)
    autocorr_30 = series.autocorr(lag=30)
    return bool(
        (pd.notna(autocorr_7) and autocorr_7 > _SEASONAL_AUTOCORR)
        or (pd.notna(autocorr_30) and autocorr_30 > _SEASONAL_AUTOCORR)
    )


def _mean_horizons(series: pd.Series) -> tuple[float, float, float]:
    """Project the recent daily average across 30, 60, and 90 days."""
    mean_val = series.mean()
    if pd.isna(mean_val):
        mean_val = 0.0
    daily = float(mean_val)
    return (
        round(daily * 30, 0),
        round(daily * 60, 0),
        round(daily * 90, 0),
    )


def forecast_horizons(
    frame: pd.DataFrame, seasonal: bool
) -> tuple[float, float, float]:
    """Forecast total units over the next 30, 60, and 90 days.

    The smoother is fit once. Each horizon is the sum of that many days,
    and any negative day is clipped to zero before the sum.
    """
    series = _remove_outliers(frame["quantity"]).reset_index(drop=True)
    if len(series) < _MIN_HISTORY_DAYS:
        return _mean_horizons(series)

    try:
        use_season = seasonal and len(series) >= _SEASONAL_HISTORY_DAYS
        if use_season:
            model = ExponentialSmoothing(
                series,
                trend="add",
                seasonal="add",
                seasonal_periods=7,
                initialization_method="estimated",
            )
        else:
            model = ExponentialSmoothing(
                series,
                trend="add",
                seasonal=None,
                initialization_method="estimated",
            )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fitted = model.fit(optimized=True)
            daily = fitted.forecast(90).clip(lower=0)
        return (
            round(float(daily.iloc[:30].sum()), 0),
            round(float(daily.iloc[:60].sum()), 0),
            round(float(daily.sum()), 0),
        )
    except Exception as exc:
        logger.warning(
            "Exponential smoothing failed, using the recent average: %s", exc
        )
        return _mean_horizons(series)


def _generate_forecast_from_data(
    sku: str,
    title: str,
    frame: pd.DataFrame,
    rule: ReorderRule | None,
    current_stock: int,
    lead_time: int,
    safety_stock: int,
) -> SKUForecast:
    """Build one forecast from data that has already been loaded."""
    velocity_30d = _calculate_velocity(frame, 30)
    velocity_90d = _calculate_velocity(frame, 90)
    velocity_365d = _calculate_velocity(frame, 365)

    if len(frame) >= 30:
        rolling = frame["quantity"].rolling(window=30).mean()
        last_val = rolling.iloc[-1]
        rolling_30d = round(float(last_val), 2) if pd.notna(last_val) else velocity_30d
    else:
        rolling_30d = velocity_30d

    has_seasonality = _detect_seasonality(frame)
    forecast_30d, forecast_60d, forecast_90d = forecast_horizons(frame, has_seasonality)

    reorder_point = compute_reorder_point(
        rolling_30d,
        lead_time,
        safety_stock,
        rule_floor=rule.reorder_point if rule else None,
    )
    below_reorder = reorder_point > 0 and current_stock <= reorder_point
    suggested_qty = suggest_order_quantity(
        rolling_30d,
        current_stock,
        below_reorder_point=below_reorder,
        minimum_quantity=rule.reorder_quantity if rule else None,
    )
    days_remaining = round(current_stock / rolling_30d, 1) if rolling_30d > 0 else None

    return SKUForecast(
        sku=sku,
        title=title,
        avg_daily_velocity_30d=velocity_30d,
        avg_daily_velocity_90d=velocity_90d,
        avg_daily_velocity_365d=velocity_365d,
        rolling_30d_avg=rolling_30d,
        forecast_30d=forecast_30d,
        forecast_60d=forecast_60d,
        forecast_90d=forecast_90d,
        has_seasonality=has_seasonality,
        reorder_point=reorder_point,
        current_stock=current_stock,
        below_reorder_point=below_reorder,
        suggested_reorder_qty=suggested_qty,
        days_of_stock_remaining=days_remaining,
        lead_time_days=lead_time,
        safety_stock=safety_stock,
    )


async def generate_forecast(session, sku: str) -> SKUForecast | None:
    """Forecast one SKU. Returns None when that SKU has no sales."""
    frame = await _get_daily_sales(session, sku, days=365)
    if frame.empty:
        return None

    product = await session.execute(select(Product.title).where(Product.sku == sku))
    title = product.scalar_one_or_none() or "Unknown"
    rule_result = await session.execute(
        select(ReorderRule).where(ReorderRule.sku == sku)
    )
    rule = rule_result.scalar_one_or_none()
    position = await position_for_sku(session, sku, "shiphero")
    current_stock = position.available if position else 0
    lead_time = rule.lead_time_days if rule else 14
    safety_stock = rule.safety_stock if rule else 0
    return _generate_forecast_from_data(
        sku, title, frame, rule, current_stock, lead_time, safety_stock
    )


async def _get_all_daily_sales(session, days: int = 365) -> dict[str, pd.DataFrame]:
    """One query for every SKU's daily sales."""
    cutoff = datetime.now(UTC) - timedelta(days=days)
    sale_day = day_bucket(Order.created_at)
    result = await session.execute(
        select(
            OrderLineItem.sku,
            sale_day.label("sale_date"),
            func.sum(OrderLineItem.quantity).label("total_qty"),
        )
        .join(Order, OrderLineItem.order_id == Order.order_id)
        .where(Order.created_at >= cutoff)
        .group_by(OrderLineItem.sku, sale_day)
        .order_by(OrderLineItem.sku, sale_day)
    )
    grouped: dict[str, list] = defaultdict(list)
    for sku, sale_date, total_qty in result.all():
        grouped[sku].append((sale_date, total_qty))
    return {sku: _rows_to_frame(rows) for sku, rows in grouped.items()}


async def generate_all_forecasts() -> list[SKUForecast]:
    """Forecast every SKU that has sales. Uses the 30-minute memory cache."""
    now = datetime.now(UTC)
    cached = _forecast_cache["data"]
    expires = _forecast_cache["expires"]
    if expires and now < expires and cached:
        return cached

    async with async_session() as session:
        sku_frames = await _get_all_daily_sales(session)
        titles_result = await session.execute(select(Product.sku, Product.title))
        titles = {sku: (title or "Unknown") for sku, title in titles_result.all()}
        rules_result = await session.execute(select(ReorderRule))
        rules = {rule.sku: rule for rule in rules_result.scalars().all()}
        stock = await positions_by_sku(session, "shiphero")

    forecasts: list[SKUForecast] = []
    for sku, frame in sku_frames.items():
        if frame.empty:
            continue
        rule = rules.get(sku)
        position = stock.get(sku)
        try:
            forecasts.append(
                _generate_forecast_from_data(
                    sku,
                    titles.get(sku, "Unknown"),
                    frame,
                    rule,
                    position.available if position else 0,
                    rule.lead_time_days if rule else 14,
                    rule.safety_stock if rule else 0,
                )
            )
        except Exception:
            logger.exception("Forecast failed for %s", sku)

    _forecast_cache["data"] = forecasts
    _forecast_cache["expires"] = now + timedelta(minutes=CACHE_TTL_MINUTES)
    below = sum(1 for item in forecasts if item.below_reorder_point)
    logger.info(
        "Generated forecasts for %s SKUs, %s at or below reorder point",
        len(forecasts),
        below,
    )
    return forecasts


async def update_reorder_rules() -> int:
    """Write forecast reorder points back onto reorder rules. Used by the nightly job."""
    forecasts = await generate_all_forecasts()
    upsert = get_upsert()
    async with async_session() as session:
        for forecast in forecasts:
            stmt = (
                upsert(ReorderRule)
                .values(
                    sku=forecast.sku,
                    reorder_point=forecast.reorder_point,
                    reorder_quantity=max(forecast.suggested_reorder_qty, 0),
                    lead_time_days=forecast.lead_time_days,
                    safety_stock=forecast.safety_stock,
                )
                .on_conflict_do_update(
                    index_elements=["sku"],
                    set_={
                        "reorder_point": forecast.reorder_point,
                        "reorder_quantity": max(forecast.suggested_reorder_qty, 0),
                    },
                )
            )
            await session.execute(stmt)
        await session.commit()
    return len(forecasts)


async def get_reorder_alerts() -> list[SKUForecast]:
    """SKUs at or below their reorder point."""
    forecasts = await generate_all_forecasts()
    return [item for item in forecasts if item.below_reorder_point]
