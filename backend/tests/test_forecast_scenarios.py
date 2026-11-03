"""Wins we are willing to keep, measured on synthetic demand.

Each test builds a situation the old Holt-Winters-only model handles badly
and checks that the replacement is actually better. A method that does not
win here does not get to be the default.
"""

import numpy as np

from app.services.forecast_engine import (
    forecast_croston,
    forecast_ets,
    forecast_sba,
    forecast_seasonal_naive,
    hierarchical_forecast,
    impute_stockouts,
    mase_scale,
    prepare_training_series,
    promo_uplift_factor,
    run_portfolio,
)


def _mase(actual: np.ndarray, pred: np.ndarray, scale_from: np.ndarray) -> float:
    scale = mase_scale(scale_from)
    mae = float(np.mean(np.abs(actual - pred)))
    if scale <= 1e-8:
        return 0.0 if mae < 1e-8 else 999.0
    return mae / scale


def _family(seed: int = 4) -> dict[str, np.ndarray]:
    """One shoe, six sizes. The parent is seasonal. The rare sizes are lumpy."""
    rng = np.random.default_rng(seed)
    t = np.arange(220)
    parent = np.clip(10 + 4 * np.sin(2 * np.pi * t / 7) + rng.normal(0, 0.3, t.size), 0, None)
    shares = np.array([0.04, 0.08, 0.18, 0.30, 0.28, 0.12])
    series = {}
    for index, share in enumerate(shares):
        draws = []
        for day in parent:
            draws.append(rng.binomial(max(int(round(day)), 0), share))
        series[f"size-{index}"] = np.asarray(draws, dtype=float)
    return series


def test_hierarchical_beats_ets_on_rare_sizes():
    series = _family()
    parents = {sku: "trainer" for sku in series}
    # Score the last 28 days only, the way the backtest does.
    horizon = 28
    actuals = {sku: values[-horizon:] for sku, values in series.items()}
    history = {sku: values[:-horizon] for sku, values in series.items()}
    hier = hierarchical_forecast(history, parents, horizon)
    weighted_hier = 0.0
    weighted_ets = 0.0
    weight = 0.0
    for sku, actual in actuals.items():
        ets = forecast_ets(history[sku], horizon)
        assert ets is not None
        w = float(np.sum(series[sku])) + 0.25
        weighted_hier += _mase(actual, hier[sku], series[sku]) * w
        weighted_ets += _mase(actual, ets, series[sku]) * w
        weight += w
    assert weighted_hier / weight < weighted_ets / weight * 0.95


def test_sba_is_the_croston_level_with_the_standard_correction():
    y = np.array([0, 0, 4, 0, 0, 0, 2, 0, 0, 5, 0, 0], dtype=float)
    croston = forecast_croston(y, 3, alpha=0.1)
    sba = forecast_sba(y, 3, alpha=0.1)
    assert np.allclose(sba, croston * (1 - 0.1 / 2))


def test_stockout_imputation_recovers_censored_demand():
    rng = np.random.default_rng(3)
    t = np.arange(180)
    latent = np.clip(6 + 2 * np.sin(2 * np.pi * t / 7) + rng.normal(0, 0.2, t.size), 0, None)
    censored = latent.copy()
    stockout = np.zeros(len(latent), dtype=bool)
    stockout[120:134] = True
    censored[stockout] = 0
    raw_fit = forecast_ets(censored[:140], 20)
    imputed = impute_stockouts(censored, stockout)
    fixed_fit = forecast_ets(imputed[:140], 20)
    assert raw_fit is not None and fixed_fit is not None
    truth = latent[140:160]
    raw_mae = float(np.mean(np.abs(raw_fit - truth)))
    fixed_mae = float(np.mean(np.abs(fixed_fit - truth)))
    assert fixed_mae < raw_mae


def test_known_promotion_lifts_the_forecast():
    rng = np.random.default_rng(5)
    y = np.clip(rng.normal(3, 0.4, 160), 0, None)
    uplift = np.ones(len(y))
    uplift[140:147] = promo_uplift_factor(25)
    y[140:147] *= uplift[140:147]
    flat = prepare_training_series(y, None)
    adjusted = prepare_training_series(y, uplift)
    # The promo week should not remain inside the training series.
    assert float(np.mean(adjusted[140:147])) < float(np.mean(flat[140:147]))


def test_ets_follows_a_trend_that_last_week_misses():
    t = np.arange(160)
    y = 1.0 + 0.04 * t
    horizon = 21
    ets = forecast_ets(y[:-horizon], horizon)
    naive = forecast_seasonal_naive(y[:-horizon], horizon)
    assert ets is not None
    assert _mase(y[-horizon:], ets, y) < _mase(y[-horizon:], naive, y)


def test_portfolio_uses_hierarchy_for_a_rare_size():
    series = _family(seed=8)
    parents = {sku: "trainer" for sku in series}
    result = run_portfolio(
        series,
        parents=parents,
        horizon=21,
        backtest_horizon=14,
        step=28,
        min_train=80,
    )
    rare = result.skus["size-0"]
    assert "hierarchical" in rare.scores
    assert rare.scores["hierarchical"].mase <= rare.scores["ets"].mase * 1.05
    point, low, high = rare.sum_between(0, 21)
    assert high >= point >= low
    # The 21-day band should not be dozens of times the point forecast.
    assert high - low < max(point * 4, 30)
