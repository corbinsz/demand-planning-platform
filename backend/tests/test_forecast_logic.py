"""Forecast cleaning, seasonality, and horizon totals."""

from datetime import datetime, timedelta

import pandas as pd
from app.services.analytics import assign_abc_class
from app.services.forecasting import (
    _detect_seasonality,
    _generate_forecast_from_data,
    _remove_outliers,
    forecast_horizons,
)


def _frame(quantities: list[float]) -> pd.DataFrame:
    end = datetime(2026, 11, 18)
    start = end - timedelta(days=len(quantities) - 1)
    return pd.DataFrame(
        {"date": pd.date_range(start, end, freq="D"), "quantity": quantities}
    )


def test_short_history_uses_the_daily_average():
    horizons = forecast_horizons(_frame([2, 2, 2, 2, 2]), seasonal=False)
    assert horizons == (60, 120, 180)


def test_outliers_are_pulled_back_to_the_mean_and_short_series_are_kept():
    cleaned = _remove_outliers(pd.Series([1] * 20 + [100]))
    assert cleaned.iloc[-1] < 20
    assert list(_remove_outliers(pd.Series([1, 100, 1]))) == [1, 100, 1]


def test_weekly_pattern_is_seasonal_and_a_flat_series_is_not():
    weekly = []
    for _ in range(10):
        weekly.extend([8, 1, 1, 1, 1, 1, 1])
    assert _detect_seasonality(_frame(weekly)) is True
    assert _detect_seasonality(_frame([3] * 70)) is False
    assert _detect_seasonality(_frame([1] * 20)) is False


def test_fitted_horizons_stay_non_negative_and_ordered():
    horizons = forecast_horizons(_frame([1] * 40), seasonal=False)
    assert horizons[0] > 0
    assert horizons[0] <= horizons[1] <= horizons[2]


def test_zero_demand_with_no_rule_is_not_a_reorder():
    forecast = _generate_forecast_from_data(
        "VE-NONE", "Quiet", _frame([0] * 20), None, 0, 14, 0
    )
    assert forecast.reorder_point == 0
    assert forecast.below_reorder_point is False
    assert forecast.days_of_stock_remaining is None


def test_reorder_fields_use_recent_demand_stock_and_the_rule_floor():
    class Rule:
        reorder_point = 5
        reorder_quantity = 10

    forecast = _generate_forecast_from_data(
        "VE-SH-FG-9",
        "Veldt Trail Shoe",
        _frame([2] * 40),
        Rule(),
        current_stock=14,
        lead_time=14,
        safety_stock=0,
    )
    assert forecast.reorder_point == 28
    assert forecast.below_reorder_point is True
    assert forecast.suggested_reorder_qty == 98
    assert forecast.days_of_stock_remaining == 7.0


def test_abc_class_keeps_the_sku_that_crosses_the_threshold():
    assert assign_abc_class(0) == "A"
    assert assign_abc_class(79.9) == "A"
    assert assign_abc_class(80) == "B"
    assert assign_abc_class(94.9) == "B"
    assert assign_abc_class(95) == "C"
