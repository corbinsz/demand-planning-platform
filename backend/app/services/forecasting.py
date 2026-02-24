import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from sqlalchemy import select, and_, func
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from app.database import async_session, get_upsert
from app.models.models import OrderLineItem, Order, ReorderRule, Product, InventorySnapshot

logger = logging.getLogger(__name__)

# In-memory forecast cache
_forecast_cache: dict = {"data": [], "expires": None}
CACHE_TTL_MINUTES = 30


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
    has_seasonality: bool
    reorder_point: int
    current_stock: int
    below_reorder_point: bool
    suggested_reorder_qty: int
    days_of_stock_remaining: float | None
    lead_time_days: int
    safety_stock: int


async def _get_daily_sales(session, sku: str, days: int = 365) -> pd.DataFrame:
    """Get daily sales aggregation for a SKU."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    result = await session.execute(
        select(
            func.strftime('%Y-%m-%d', Order.created_at).label("sale_date"),
            func.sum(OrderLineItem.quantity).label("total_qty"),
        )
        .join(Order, OrderLineItem.order_id == Order.order_id)
        .where(
            and_(
                OrderLineItem.sku == sku,
                Order.created_at >= cutoff,
            )
        )
        .group_by(func.strftime('%Y-%m-%d', Order.created_at))
        .order_by(func.strftime('%Y-%m-%d', Order.created_at))
    )
    rows = result.all()

    if not rows:
        return pd.DataFrame(columns=["date", "quantity"])

    df = pd.DataFrame(rows, columns=["date", "quantity"])
    df["date"] = pd.to_datetime(df["date"])

    # Fill missing days with 0
    date_range = pd.date_range(start=df["date"].min(), end=df["date"].max(), freq="D")
    df = df.set_index("date").reindex(date_range, fill_value=0).reset_index()
    df.columns = ["date", "quantity"]
    return df


def _remove_outliers(series: pd.Series, z_threshold: float = 3.0) -> pd.Series:
    """Remove outliers using z-score method."""
    if len(series) < 10:
        return series.astype(float)
    mean = series.mean()
    std = series.std()
    if std == 0:
        return series.astype(float)
    z_scores = np.abs((series - mean) / std)
    cleaned = series.astype(float).copy()
    cleaned[z_scores > z_threshold] = mean
    return cleaned


def _calculate_velocity(df: pd.DataFrame, days: int) -> float:
    """Calculate average daily velocity over N most recent days."""
    if df.empty:
        return 0.0
    recent = df.tail(days)
    return round(recent["quantity"].mean(), 2)


def _detect_seasonality(df: pd.DataFrame) -> bool:
    """Simple seasonality detection using autocorrelation."""
    if len(df) < 60:
        return False
    series = df["quantity"]
    if series.std() == 0:
        return False
    autocorr_7 = series.autocorr(lag=7)
    autocorr_30 = series.autocorr(lag=30)
    return bool(
        (pd.notna(autocorr_7) and autocorr_7 > 0.3)
        or (pd.notna(autocorr_30) and autocorr_30 > 0.3)
    )


def _exponential_smoothing_forecast(
    df: pd.DataFrame, periods: int, seasonal: bool
) -> float:
    """Apply exponential smoothing and forecast N days ahead."""
    series = _remove_outliers(df["quantity"])

    if len(series) < 14:
        mean_val = series.mean()
        if pd.isna(mean_val):
            return 0.0
        return round(mean_val * periods, 0)

    try:
        if seasonal and len(series) >= 60:
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
                initialization_method="estimated",
            )
        fitted = model.fit(optimized=True)
        forecast = fitted.forecast(periods)
        return round(max(forecast.sum(), 0), 0)
    except Exception as e:
        logger.warning(f"Exponential smoothing failed, falling back to average: {e}")
        mean_val = series.mean()
        if pd.isna(mean_val):
            return 0.0
        return round(mean_val * periods, 0)


async def generate_forecast(session, sku: str) -> SKUForecast | None:
    """Generate a complete forecast for a single SKU (uses shared session)."""
    df = await _get_daily_sales(session, sku, days=365)
    if df.empty:
        return None

    # Get product title
    product = await session.execute(
        select(Product.title).where(Product.sku == sku)
    )
    title = product.scalar_one_or_none() or "Unknown"

    # Get reorder rules
    rule_result = await session.execute(
        select(ReorderRule).where(ReorderRule.sku == sku)
    )
    rule = rule_result.scalar_one_or_none()

    # Get current stock from latest ShipHero snapshot
    stock_result = await session.execute(
        select(func.sum(InventorySnapshot.quantity_available))
        .where(
            and_(
                InventorySnapshot.sku == sku,
                InventorySnapshot.source == "shiphero",
            )
        )
    )
    current_stock = stock_result.scalar_one() or 0

    lead_time = rule.lead_time_days if rule else 14
    safety_stock = rule.safety_stock if rule else 0

    return _generate_forecast_from_data(sku, title, df, rule, current_stock, lead_time, safety_stock)


def _generate_forecast_from_data(
    sku: str,
    title: str,
    df: pd.DataFrame,
    rule,
    current_stock: int,
    lead_time: int,
    safety_stock: int,
) -> SKUForecast:
    """Pure computation — build a SKUForecast from pre-fetched data (no DB queries)."""
    velocity_30d = _calculate_velocity(df, 30)
    velocity_90d = _calculate_velocity(df, 90)
    velocity_365d = _calculate_velocity(df, 365)

    # Rolling 30-day average
    if len(df) >= 30:
        rolling = df["quantity"].rolling(window=30).mean()
        last_val = rolling.iloc[-1]
        rolling_30d = round(last_val, 2) if pd.notna(last_val) else velocity_30d
    else:
        rolling_30d = velocity_30d

    has_seasonality = _detect_seasonality(df)

    forecast_30d = _exponential_smoothing_forecast(df, 30, has_seasonality)
    forecast_60d = _exponential_smoothing_forecast(df, 60, has_seasonality)
    forecast_90d = _exponential_smoothing_forecast(df, 90, has_seasonality)

    # Reorder point = (avg daily sales x lead_time_days) + safety_stock
    reorder_point = int(np.ceil(rolling_30d * lead_time) + safety_stock)
    if rule:
        reorder_point = max(reorder_point, rule.reorder_point)

    below_reorder = current_stock <= reorder_point

    # Suggested reorder qty: weeks_of_supply_target (default 8 weeks)
    weeks_target = 8
    suggested_qty = max(
        int(np.ceil(rolling_30d * 7 * weeks_target)) - current_stock, 0
    )
    if rule and rule.reorder_quantity:
        suggested_qty = max(suggested_qty, rule.reorder_quantity)

    days_remaining = (
        round(current_stock / rolling_30d, 1) if rolling_30d > 0 else None
    )

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


# ---- Batch query helpers for generate_all_forecasts ----

async def _get_all_daily_sales(session, days: int = 365) -> dict[str, pd.DataFrame]:
    """Single query for ALL SKU daily sales, grouped into per-SKU DataFrames."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    result = await session.execute(
        select(
            OrderLineItem.sku,
            func.strftime('%Y-%m-%d', Order.created_at).label("sale_date"),
            func.sum(OrderLineItem.quantity).label("total_qty"),
        )
        .join(Order, OrderLineItem.order_id == Order.order_id)
        .where(Order.created_at >= cutoff)
        .group_by(OrderLineItem.sku, func.strftime('%Y-%m-%d', Order.created_at))
        .order_by(OrderLineItem.sku, func.strftime('%Y-%m-%d', Order.created_at))
    )
    rows = result.all()

    # Group rows by SKU
    sku_rows: dict[str, list] = defaultdict(list)
    for sku, sale_date, total_qty in rows:
        sku_rows[sku].append((sale_date, total_qty))

    # Build per-SKU DataFrames with gap-filling
    sku_dfs: dict[str, pd.DataFrame] = {}
    for sku, data in sku_rows.items():
        df = pd.DataFrame(data, columns=["date", "quantity"])
        df["date"] = pd.to_datetime(df["date"])
        date_range = pd.date_range(start=df["date"].min(), end=df["date"].max(), freq="D")
        df = df.set_index("date").reindex(date_range, fill_value=0).reset_index()
        df.columns = ["date", "quantity"]
        sku_dfs[sku] = df

    return sku_dfs


async def _get_all_titles(session) -> dict[str, str]:
    """All product titles in one query."""
    result = await session.execute(select(Product.sku, Product.title))
    return {sku: (title or "Unknown") for sku, title in result.all()}


async def _get_all_reorder_rules(session) -> dict[str, ReorderRule]:
    """All reorder rules in one query."""
    result = await session.execute(select(ReorderRule))
    return {rule.sku: rule for rule in result.scalars().all()}


async def _get_all_stock(session) -> dict[str, int]:
    """Latest inventory snapshot per SKU in one query."""
    result = await session.execute(
        select(
            InventorySnapshot.sku,
            func.sum(InventorySnapshot.quantity_available).label("total_stock"),
        )
        .where(InventorySnapshot.source == "shiphero")
        .group_by(InventorySnapshot.sku)
    )
    return {sku: (stock or 0) for sku, stock in result.all()}


async def generate_all_forecasts() -> list[SKUForecast]:
    """Generate forecasts for all active SKUs (cached). Uses batch queries."""
    now = datetime.now(timezone.utc)
    if _forecast_cache["expires"] and now < _forecast_cache["expires"] and _forecast_cache["data"]:
        return _forecast_cache["data"]

    async with async_session() as session:
        # 4 batch queries instead of 4N+1 per-SKU queries
        sku_dfs = await _get_all_daily_sales(session)
        titles = await _get_all_titles(session)
        rules = await _get_all_reorder_rules(session)
        stock = await _get_all_stock(session)

    # Get the union of all SKUs that have sales data
    skus_with_sales = set(sku_dfs.keys())

    forecasts = []
    for sku in skus_with_sales:
        df = sku_dfs[sku]
        if df.empty:
            continue

        title = titles.get(sku, "Unknown")
        rule = rules.get(sku)
        current_stock = stock.get(sku, 0)
        lead_time = rule.lead_time_days if rule else 14
        safety_stock_val = rule.safety_stock if rule else 0

        forecast = _generate_forecast_from_data(
            sku, title, df, rule, current_stock, lead_time, safety_stock_val
        )
        forecasts.append(forecast)

    _forecast_cache["data"] = forecasts
    _forecast_cache["expires"] = now + timedelta(minutes=CACHE_TTL_MINUTES)

    logger.info(
        f"Generated forecasts for {len(forecasts)} SKUs, "
        f"{sum(1 for f in forecasts if f.below_reorder_point)} below reorder point"
    )
    return forecasts


async def update_reorder_rules() -> int:
    """Update reorder rules from forecasts (called by scheduler only, not GET requests)."""
    forecasts = await generate_all_forecasts()

    upsert = get_upsert()
    async with async_session() as session:
        for f in forecasts:
            stmt = (
                upsert(ReorderRule)
                .values(
                    sku=f.sku,
                    reorder_point=f.reorder_point,
                    reorder_quantity=f.suggested_reorder_qty,
                    lead_time_days=f.lead_time_days,
                    safety_stock=f.safety_stock,
                )
                .on_conflict_do_update(
                    index_elements=["sku"],
                    set_={
                        "reorder_point": f.reorder_point,
                        "reorder_quantity": f.suggested_reorder_qty,
                    },
                )
            )
            await session.execute(stmt)
        await session.commit()

    return len(forecasts)


async def get_reorder_alerts() -> list[SKUForecast]:
    """Return only SKUs below their reorder point."""
    forecasts = await generate_all_forecasts()
    return [f for f in forecasts if f.below_reorder_point]
