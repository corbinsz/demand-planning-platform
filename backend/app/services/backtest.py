"""Rolling-origin accuracy of the shipped 30-day forecast.

Each holdout is the next 30 days of unit sales. The newest 30 days are
always scored when 120 days of history come before them. Earlier holdouts
step back 60 days at a time, so the windows do not overlap. Holt-Winters is
the same ``forecast_horizons`` path the app uses to plan a buy. The baseline
repeats the last 7 days (seasonal naive).

WAPE is total absolute error divided by total actual units, so a high-volume
SKU counts more than a quiet one. Bias is total forecast minus total actual,
divided by total actual. Positive bias means the forecast was too high.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pandas as pd
from sqlalchemy import select

from app.database import async_session
from app.models.models import Product
from app.services.forecasting import (
    _detect_seasonality,
    _get_all_daily_sales,
    forecast_horizons,
)

logger = logging.getLogger(__name__)

HORIZON_DAYS = 30
MIN_TRAIN_DAYS = 120
ORIGIN_STEP_DAYS = 60
SEASONAL_PERIOD = 7
CACHE_TTL_MINUTES = 30


@dataclass
class ModelScore:
    """Volume-weighted error for one model."""

    wape: float | None
    bias: float | None


@dataclass
class SkuBacktest:
    """Accuracy for one SKU across its holdouts."""

    sku: str
    title: str
    origins: int
    actual_units: int
    holt_winters: ModelScore
    seasonal_naive: ModelScore


@dataclass
class BacktestReport:
    """Catalog-level backtest plus one row per scored SKU."""

    horizon_days: int
    origin_step_days: int
    min_train_days: int
    seasonal_period: int
    evaluated_origins: int
    sku_count: int
    skipped_skus: int
    holt_winters: ModelScore
    seasonal_naive: ModelScore
    skus: list[SkuBacktest]
    note: str


_cached_report: BacktestReport | None = None
_cache_expires: datetime | None = None


def clear_backtest_cache() -> None:
    """Drop the cached report. Tests call this between cases."""
    global _cached_report, _cache_expires
    _cached_report = None
    _cache_expires = None


def origin_ends(length: int) -> list[int]:
    """Training lengths whose 30-day holdouts sit inside ``length`` rows.

    The newest holdout is included when at least ``MIN_TRAIN_DAYS`` rows
    precede it. Older holdouts step back by ``ORIGIN_STEP_DAYS``.
    """
    latest = length - HORIZON_DAYS
    if latest < MIN_TRAIN_DAYS:
        return []
    ends: list[int] = []
    end = latest
    while end >= MIN_TRAIN_DAYS:
        ends.append(end)
        end -= ORIGIN_STEP_DAYS
    ends.reverse()
    return ends


def seasonal_naive_total(history: pd.Series, horizon: int, period: int) -> float:
    """Sum of a seasonal-naive forecast over the next ``horizon`` days.

    Day ``h`` copies the observation ``period`` days earlier, walking back
    whole seasons until it lands in history. A series shorter than one
    season uses its mean instead.
    """
    values = history.astype(float).to_numpy()
    if len(values) == 0 or horizon <= 0:
        return 0.0
    if len(values) < period or period <= 0:
        return float(values.mean()) * horizon
    total = 0.0
    last = len(values) - 1
    for step in range(1, horizon + 1):
        cycles = math.ceil(step / period)
        offset = step - period * cycles
        total += float(values[last + offset])
    return total


def metrics_from_pairs(pairs: list[tuple[float, float]]) -> ModelScore:
    """WAPE and bias from ``(actual, forecast)`` pairs.

    Both are ``None`` when nothing was actually sold, because the
    percentages would divide by zero.
    """
    actual = 0.0
    abs_error = 0.0
    signed_error = 0.0
    for truth, forecast in pairs:
        actual += truth
        abs_error += abs(forecast - truth)
        signed_error += forecast - truth
    return ModelScore(wape=_ratio(abs_error, actual), bias=_ratio(signed_error, actual))


def _ratio(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def _score_frame(
    frame: pd.DataFrame,
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]] | None:
    """Holdout pairs for one daily series. ``None`` when no origin fits."""
    ends = origin_ends(len(frame))
    if not ends:
        return None
    holt: list[tuple[float, float]] = []
    naive: list[tuple[float, float]] = []
    for end in ends:
        train = frame.iloc[:end]
        actual = float(frame.iloc[end : end + HORIZON_DAYS]["quantity"].sum())
        seasonal = _detect_seasonality(train)
        holt_forecast = float(forecast_horizons(train, seasonal)[0])
        naive_forecast = seasonal_naive_total(
            train["quantity"], HORIZON_DAYS, SEASONAL_PERIOD
        )
        holt.append((actual, holt_forecast))
        naive.append((actual, naive_forecast))
    return holt, naive


def backtest_frames(
    frames: dict[str, pd.DataFrame], titles: dict[str, str]
) -> BacktestReport:
    """Score every series that has a full holdout."""
    holt_pairs: list[tuple[float, float]] = []
    naive_pairs: list[tuple[float, float]] = []
    rows: list[SkuBacktest] = []
    skipped = 0
    for sku in sorted(frames):
        frame = frames[sku]
        try:
            scored = _score_frame(frame)
        except Exception:
            logger.exception("Backtest failed for %s", sku)
            skipped += 1
            continue
        if scored is None:
            skipped += 1
            continue
        holt, naive = scored
        holt_pairs.extend(holt)
        naive_pairs.extend(naive)
        rows.append(
            SkuBacktest(
                sku=sku,
                title=titles.get(sku) or sku,
                origins=len(holt),
                actual_units=int(round(sum(actual for actual, _ in holt))),
                holt_winters=metrics_from_pairs(holt),
                seasonal_naive=metrics_from_pairs(naive),
            )
        )
    rows.sort(
        key=lambda row: (
            row.holt_winters.wape is None,
            -(row.holt_winters.wape or 0),
            row.sku,
        )
    )
    return BacktestReport(
        horizon_days=HORIZON_DAYS,
        origin_step_days=ORIGIN_STEP_DAYS,
        min_train_days=MIN_TRAIN_DAYS,
        seasonal_period=SEASONAL_PERIOD,
        evaluated_origins=len(holt_pairs),
        sku_count=len(rows),
        skipped_skus=skipped,
        holt_winters=metrics_from_pairs(holt_pairs),
        seasonal_naive=metrics_from_pairs(naive_pairs),
        skus=rows,
        note=(
            "Rolling-origin backtest on the orders in this database. "
            "The bundled catalog is synthetic, so these errors are not a result from a live store."
        ),
    )


async def run_backtest() -> BacktestReport:
    """Score the catalog. The fit is cached for 30 minutes."""
    global _cached_report, _cache_expires
    now = datetime.now(UTC)
    if (
        _cached_report is not None
        and _cache_expires is not None
        and now < _cache_expires
    ):
        return _cached_report

    async with async_session() as session:
        frames = await _get_all_daily_sales(session)
        title_rows = await session.execute(select(Product.sku, Product.title))
        titles = {sku: title or sku for sku, title in title_rows.all()}

    started = time.perf_counter()
    report = await asyncio.to_thread(backtest_frames, frames, titles)
    logger.info(
        "Backtest scored %s SKUs (%s origins) in %.1fs. Holt-Winters WAPE=%s, seasonal naive WAPE=%s",
        report.sku_count,
        report.evaluated_origins,
        time.perf_counter() - started,
        report.holt_winters.wape,
        report.seasonal_naive.wape,
    )
    _cached_report = report
    _cache_expires = now + timedelta(minutes=CACHE_TTL_MINUTES)
    return report
