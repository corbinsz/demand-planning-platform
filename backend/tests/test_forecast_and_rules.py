"""Unit tests for forecast math, reorder rules, and ABC boundaries."""

import hashlib
import hmac

import numpy as np
import pytest

from app.security import decrypt_secret, encrypt_secret, verify_shopify_hmac
from app.services.analytics import classify_abc
from app.services.forecast_engine import (
    forecast_croston,
    forecast_seasonal_naive,
    forecast_tsb,
    is_intermittent,
    prepare_training_series,
    promo_uplift_factor,
    run_portfolio,
)
from app.services.reorder import compute_reorder
from app.services.shopify_oauth import normalize_shop


def test_reorder_moq_does_not_apply_when_stock_is_healthy():
    plan = compute_reorder(
        daily_demand=1,
        current_stock=500,
        lead_time_days=14,
        safety_stock=5,
        moq=200,
        manual_reorder_point=20,
    )
    assert plan["below_reorder_point"] is False
    assert plan["suggested_reorder_qty"] == 0


def test_reorder_skips_moq_when_it_would_bury_a_slow_seller():
    plan = compute_reorder(
        daily_demand=0.07,
        current_stock=0,
        lead_time_days=21,
        safety_stock=0,
        moq=150,
    )
    assert plan["suggested_reorder_qty"] < 20


def test_reorder_applies_moq_only_when_buying():
    plan = compute_reorder(
        daily_demand=2,
        current_stock=3,
        lead_time_days=14,
        safety_stock=0,
        moq=80,
    )
    assert plan["below_reorder_point"] is True
    assert plan["suggested_reorder_qty"] >= 80


def test_abc_hero_is_class_a_even_if_it_is_most_of_revenue():
    assert classify_abc(0) == "A"
    assert classify_abc(79.9) == "A"
    assert classify_abc(80) == "B"
    assert classify_abc(95) == "C"


def test_croston_holds_through_zeros_and_tsb_fades():
    quiet = np.array([0, 0, 0, 5, 0, 0, 0, 4, 0, 0, 0, 0], dtype=float)
    assert is_intermittent(quiet)
    assert forecast_croston(quiet, 4)[0] > 0
    recent = np.array([0, 5, 0, 5, 0, 5], dtype=float)
    stale = np.concatenate([np.array([5, 0, 5, 0, 5], dtype=float), np.zeros(40)])
    assert forecast_tsb(stale, 1)[0] < forecast_tsb(recent, 1)[0]
    fresh = forecast_croston(np.array([5.0, 0, 5, 0, 5]), 1)[0]
    held = forecast_croston(np.concatenate([np.array([5.0, 0, 5, 0, 5]), np.zeros(30)]), 1)[0]
    assert abs(fresh - held) < 1e-9


def test_promo_days_do_not_become_the_baseline():
    raw = np.array([2, 2, 2, 2, 2, 2, 2, 40, 2, 2, 2, 2, 2, 2], dtype=float)
    uplift = np.ones(len(raw))
    uplift[7] = promo_uplift_factor(25)
    adjusted = prepare_training_series(raw, uplift, start_dow=0)
    assert adjusted[7] < 10
    assert forecast_seasonal_naive(adjusted, 7)[0] < 20


def test_portfolio_picks_a_finite_model_and_nonnegative_band():
    rng = np.random.default_rng(1)
    t = np.arange(180)
    seasonal = np.clip(4 + np.sin(t / 7 * 2 * np.pi) * 1.5 + rng.normal(0, 0.2, len(t)), 0, None)
    intermittent = np.zeros(180)
    intermittent[::12] = 6
    result = run_portfolio(
        {"seasonal": seasonal, "sparse": intermittent},
        horizon=30,
        backtest_horizon=14,
        step=21,
        min_train=70,
    )
    assert set(result.skus) == {"seasonal", "sparse"}
    for forecast in result.skus.values():
        assert forecast.model
        assert np.all(forecast.point >= 0)
        assert np.all(forecast.lower >= 0)
        assert np.all(forecast.upper >= forecast.lower)
        point, low, high = forecast.sum_between(0, 30)
        assert high + 1e-6 >= point >= low - 1e-6
    assert result.baseline_mase >= 0
    assert result.selected_mase >= 0


def test_encryption_roundtrip_and_shopify_hmac():
    secret = "store-token-value"
    blob = encrypt_secret(secret)
    assert secret not in blob
    assert decrypt_secret(blob) == secret
    params = {"code": "abc", "shop": "northline.myshopify.com", "state": "xyz", "timestamp": "1"}
    message = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    digest = hmac.new(b"app-secret", message.encode(), hashlib.sha256).hexdigest()
    assert verify_shopify_hmac({**params, "hmac": digest}, "app-secret")
    assert not verify_shopify_hmac({**params, "hmac": "deadbeef"}, "app-secret")


def test_shop_domain_normalization():
    assert normalize_shop("Northline") == "northline.myshopify.com"
    assert normalize_shop("https://northline.myshopify.com/admin") == "northline.myshopify.com"
    with pytest.raises(ValueError):
        normalize_shop("not a shop")
