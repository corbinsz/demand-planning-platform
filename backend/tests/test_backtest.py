"""Rolling-origin backtest: schedule, seasonal naive, and pooled error."""

from datetime import datetime, timedelta

import pandas as pd
from app.services.backtest import (
    backtest_frames,
    metrics_from_pairs,
    origin_ends,
    seasonal_naive_total,
)


def _frame(quantities: list[float]) -> pd.DataFrame:
    end = datetime(2026, 11, 18)
    start = end - timedelta(days=len(quantities) - 1)
    return pd.DataFrame(
        {"date": pd.date_range(start, end, freq="D"), "quantity": quantities}
    )


def test_origins_cover_the_newest_month_and_step_back_without_overlap():
    assert origin_ends(149) == []
    assert origin_ends(150) == [120]
    assert origin_ends(365) == [155, 215, 275, 335]
    ends = origin_ends(365)
    for earlier, later in zip(ends, ends[1:], strict=False):
        assert later - earlier >= 30


def test_seasonal_naive_repeats_the_last_week():
    week = [1, 2, 3, 4, 5, 6, 7]
    history = pd.Series(week * 4)
    assert seasonal_naive_total(history, horizon=7, period=7) == 28
    assert seasonal_naive_total(history, horizon=8, period=7) == 29
    assert seasonal_naive_total(history, horizon=30, period=7) == 115
    assert seasonal_naive_total(pd.Series([4, 6]), horizon=30, period=7) == 150


def test_wape_weights_by_units_and_bias_is_signed():
    score = metrics_from_pairs([(100, 110), (300, 210)])
    assert score.wape == 0.25
    assert score.bias == -0.2
    empty = metrics_from_pairs([(0, 5)])
    assert empty.wape is None
    assert empty.bias is None


def test_flat_series_matches_the_baseline_and_a_level_shift_is_not_leaked():
    flat = backtest_frames(
        {"VE-FLAT": _frame([2] * 150)},
        {"VE-FLAT": "Flat Tee"},
    )
    assert flat.sku_count == 1
    assert flat.evaluated_origins == 1
    assert flat.skus[0].actual_units == 60
    assert flat.seasonal_naive.wape == 0
    assert flat.holt_winters.wape is not None
    assert flat.holt_winters.wape < 0.1

    shifted = _frame([1] * 120 + [20] * 30)
    leaked = backtest_frames({"VE-SHIFT": shifted}, {"VE-SHIFT": "Shift"})
    assert leaked.skus[0].actual_units == 600
    assert leaked.holt_winters.wape is not None
    assert leaked.holt_winters.wape > 0.5


def test_short_series_are_skipped_and_errors_pool_across_skus():
    report = backtest_frames(
        {
            "VE-A": _frame([2] * 150),
            "VE-B": _frame([4] * 150),
            "VE-SHORT": _frame([9] * 40),
        },
        {"VE-A": "A", "VE-B": "B"},
    )
    assert report.skipped_skus == 1
    assert report.sku_count == 2
    assert report.evaluated_origins == 2
    assert report.seasonal_naive.wape == 0
    assert [row.sku for row in report.skus] == ["VE-A", "VE-B"]


def test_the_worse_sku_is_listed_first():
    report = backtest_frames(
        {
            "VE-FLAT": _frame([2] * 150),
            "VE-SHIFT": _frame([1] * 120 + [20] * 30),
        },
        {},
    )
    assert [row.sku for row in report.skus] == ["VE-SHIFT", "VE-FLAT"]
