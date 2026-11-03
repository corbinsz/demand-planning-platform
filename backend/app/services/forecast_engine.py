"""Forecast models and a rolling-origin backtest.

No database access. Callers pass one daily quantity array per SKU.

Models
------
seasonal_naive
    Repeat the last week. Strong baseline. Hard to beat on short series.
ets
    Additive Holt-Winters (statsmodels), weekly seasonality when the
    history is long enough. This is the model the app used to run for
    every SKU.
croston
    Croston's method. Meant for intermittent demand (lots of zero days).
tsb
    Teunter-Syntetos-Babai. Like Croston, but the chance of a sale decays
    during quiet stretches, so obsolete SKUs fade instead of sticking.
hgb_sku
    Gradient boosting on lag features, fit on this SKU alone.
hgb_global
    The same boosting model, fit on every SKU together so sparse sizes
    borrow strength from the rest of the catalog.

Selection
---------
Each model is scored with rolling-origin backtests (train, forecast the
next few weeks, step forward, repeat). The error we rank on is MASE:
absolute error divided by the error of a seasonal naive forecast. 1.0
means "no better than repeating last week."

A single global winner is the model with the best demand-weighted MASE
across the catalog. A SKU keeps its own winner only when that winner
beats the global model on that SKU by at least 5%. Otherwise we use the
global winner, which is less jumpy.

Confidence
----------
The 80% band comes from the backtest residuals of the chosen model
(empirical 10th/90th percentile when we have enough points). The lower
bound is never negative.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

# hgb_sku stays out of the default race: it was slower than the global
# booster and lost on every scenario we measured. hgb_global is the pooled
# histogram gradient booster (same family as LightGBM) with lag, calendar,
# and parent features.
SKU_MODELS = ("seasonal_naive", "ets", "croston", "sba", "tsb")
GLOBAL_MODEL = "hgb_global"
HIERARCHICAL_MODEL = "hierarchical"
ALL_MODELS = SKU_MODELS + (GLOBAL_MODEL, HIERARCHICAL_MODEL)

_SEASON = 7


@dataclass
class ModelScore:
    model: str
    mase: float
    rmse: float
    bias: float
    n_origins: int

    def as_dict(self) -> dict:
        return {
            "model": self.model,
            "mase": _round(self.mase),
            "rmse": _round(self.rmse),
            "bias": _round(self.bias),
            "n_origins": self.n_origins,
        }


@dataclass
class SkuForecast:
    sku: str
    model: str
    selection: str
    point: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    mase: float
    rmse: float
    intermittent: bool
    has_seasonality: bool
    q_low: float = 0.0
    q_high: float = 0.0
    scores: dict[str, ModelScore] = field(default_factory=dict)

    def sum_between(self, start: int, end: int) -> tuple[float, float, float]:
        """Horizon total, with a band that grows like sqrt(days).

        Adding the same daily error to every day treats the misses as
        perfectly correlated and makes a 30-day range look absurdly wide.
        """
        horizon = max(end - start, 1)
        point = float(np.sum(self.point[start:end]))
        scale = float(np.sqrt(horizon))
        low = max(0.0, point + float(self.q_low) * scale)
        high = max(point, point + float(self.q_high) * scale)
        return point, low, high


@dataclass
class PortfolioResult:
    global_winner: str
    global_mase: dict[str, float]
    unweighted_mase: dict[str, float]
    baseline_mase: float
    selected_mase: float
    per_sku_wins: int
    global_wins: int
    skus: dict[str, SkuForecast]

    def report(self) -> dict:
        return {
            "global_winner": self.global_winner,
            "global_mase": {k: _round(v) for k, v in self.global_mase.items()},
            "unweighted_mase": {k: _round(v) for k, v in self.unweighted_mase.items()},
            "baseline_ets_mase": _round(self.baseline_mase),
            "selected_mase": _round(self.selected_mase),
            "per_sku_wins": self.per_sku_wins,
            "global_wins": self.global_wins,
            "sku_count": len(self.skus),
            "lift_vs_ets": _round(self.baseline_mase - self.selected_mase),
        }


def _round(value: float) -> float | None:
    if value is None or not np.isfinite(value):
        return None
    return round(float(value), 4)


def _as_float(y) -> np.ndarray:
    arr = np.asarray(y, dtype=float).reshape(-1)
    return np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)


def is_intermittent(y: np.ndarray) -> bool:
    """True when a lot of days are zero.

    Classic Syntetos-Boylan also looks at size variation. For buying
    decisions, long gaps matter even when each order is the same size,
    because a smooth model treats the zeros as a falling trend.
    """
    if len(y) == 0 or not np.any(y > 0):
        return True
    return bool(float(np.mean(y <= 0)) >= 0.4)


def has_weekly_seasonality(y: np.ndarray) -> bool:
    if len(y) < 28:
        return False
    if float(np.std(y)) == 0:
        return False
    series = y - np.mean(y)
    denom = float(np.dot(series, series))
    if denom <= 0:
        return False
    corr = float(np.dot(series[:-_SEASON], series[_SEASON:]) / denom)
    return bool(np.isfinite(corr) and corr > 0.3)


def mase_scale(y: np.ndarray, season: int = _SEASON) -> float:
    if len(y) <= season:
        diffs = np.abs(np.diff(y)) if len(y) > 1 else np.array([0.0])
        return float(np.mean(diffs))
    return float(np.mean(np.abs(y[season:] - y[:-season])))


def promo_uplift_factor(discount_pct: float) -> float:
    """Demand multiplier while a promotion is running.

    A zero-discount launch still gets a small bump. Discounted events
    scale with the discount and are capped so one sale cannot explode
    the buy recommendation.
    """
    if discount_pct <= 0:
        return 1.10
    return float(1.0 + min(0.80, (discount_pct / 100.0) * 1.5))


def _weekday_baseline(raw: np.ndarray, promo: np.ndarray, start_dow: int) -> np.ndarray:
    """Replace promoted days with the typical same-weekday non-promo level."""
    y = raw.astype(float).copy()
    if not promo.any():
        return y
    for dow in range(7):
        day_is = ((start_dow + np.arange(len(y))) % 7) == dow
        normal = day_is & ~promo
        promoted = day_is & promo
        if not promoted.any():
            continue
        if normal.any():
            fill = float(np.median(y[normal]))
        elif (~promo).any():
            fill = float(np.median(y[~promo]))
        else:
            fill = float(np.median(y))
        y[promoted] = fill
    return y


def prepare_training_series(
    raw: np.ndarray,
    uplift: np.ndarray | None,
    start_dow: int = 0,
    stockout: np.ndarray | None = None,
) -> np.ndarray:
    raw = _as_float(raw)
    if stockout is not None:
        raw = impute_stockouts(raw, stockout, start_dow)
    if uplift is None:
        return raw
    uplift = np.asarray(uplift, dtype=float)
    if len(uplift) != len(raw):
        raise ValueError("uplift calendar must match the history length")
    return _weekday_baseline(raw, uplift > 1.001, start_dow)


def _cap(pred: np.ndarray, history: np.ndarray) -> np.ndarray:
    pred = np.nan_to_num(np.asarray(pred, dtype=float), nan=0.0)
    pred = np.clip(pred, 0, None)
    ceiling = max(float(np.max(history)) * 5.0 if len(history) else 1.0, 1.0)
    return np.minimum(pred, ceiling)


def _winsorize(y: np.ndarray, z: float = 3.0) -> np.ndarray:
    if len(y) < 10:
        return y.astype(float)
    mu = float(np.mean(y))
    sd = float(np.std(y))
    if sd == 0:
        return y.astype(float)
    out = y.astype(float).copy()
    out[np.abs(y - mu) > z * sd] = mu
    return out


def forecast_seasonal_naive(y: np.ndarray, horizon: int) -> np.ndarray:
    y = _as_float(y)
    if len(y) >= _SEASON:
        pattern = y[-_SEASON:]
        reps = int(np.ceil(horizon / _SEASON))
        return _cap(np.tile(pattern, reps)[:horizon], y)
    mu = float(np.mean(y)) if len(y) else 0.0
    return np.full(horizon, max(mu, 0.0))


def _croston_level(y: np.ndarray, alpha: float) -> float:
    """Smoothed demand size divided by the smoothed gap between demands."""
    z = 0.0
    p = 0.0
    q = 0
    started = False
    for value in y:
        q += 1
        if value > 0:
            if not started:
                z = float(value)
                p = float(q)
                started = True
            else:
                z = z + alpha * (float(value) - z)
                p = p + alpha * (float(q) - p)
            q = 0
    if not started or p <= 0:
        return 0.0
    return max(z / p, 0.0)


def forecast_croston(y: np.ndarray, horizon: int, alpha: float = 0.1) -> np.ndarray:
    """Classic Croston: smooth demand size and the gap between demands."""
    y = _as_float(y)
    rate = _croston_level(y, alpha)
    return _cap(np.full(horizon, rate), y)


def forecast_sba(y: np.ndarray, horizon: int, alpha: float = 0.1) -> np.ndarray:
    """Syntetos-Boylan approximation.

    Croston is biased high. SBA multiplies by (1 - alpha/2), which is the
    usual correction for intermittent demand.
    """
    y = _as_float(y)
    rate = _croston_level(y, alpha) * (1.0 - alpha / 2.0)
    return _cap(np.full(horizon, max(rate, 0.0)), y)


def impute_stockouts(y: np.ndarray, stockout: np.ndarray, start_dow: int = 0) -> np.ndarray:
    """Replace stockout days with the usual same-weekday demand.

    A zero on a day the warehouse was empty is censored demand, not a
    true zero. Filling it stops the model from learning 'we stopped selling'.
    """
    raw = _as_float(y)
    mask = np.asarray(stockout, dtype=bool)
    if mask.shape != raw.shape or not mask.any():
        return raw
    return _weekday_baseline(raw, mask, start_dow)


def hierarchical_forecast(
    series: dict[str, np.ndarray],
    parents: dict[str, str],
    horizon: int,
) -> dict[str, np.ndarray]:
    """Top-down: forecast the parent, split by recent child share.

    A rare size inherits the parent's seasonality instead of being fit
    on a string of zeros.
    """
    groups: dict[str, list[str]] = {}
    for sku in series:
        parent = parents.get(sku) or sku
        groups.setdefault(parent, []).append(sku)
    out: dict[str, np.ndarray] = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        stacked = np.sum([_as_float(series[sku]) for sku in members], axis=0)
        parent_fc = forecast_ets(stacked, horizon)
        if parent_fc is None:
            parent_fc = forecast_seasonal_naive(stacked, horizon)
        window = min(28, len(stacked))
        weights = [float(np.sum(_as_float(series[sku])[-window:])) for sku in members]
        total = sum(weights)
        if total <= 0:
            share = [1.0 / len(members)] * len(members)
        else:
            share = [w / total for w in weights]
        for sku, portion in zip(members, share, strict=True):
            out[sku] = _cap(parent_fc * portion, series[sku])
    return out


def forecast_tsb(y: np.ndarray, horizon: int, alpha: float = 0.1, beta: float = 0.1) -> np.ndarray:
    """TSB: update sale probability every day, size only when a sale happens."""
    y = _as_float(y)
    if len(y) == 0 or not np.any(y > 0):
        return np.zeros(horizon)
    p = 0.0
    z = 0.0
    started = False
    for value in y:
        occurred = 1.0 if value > 0 else 0.0
        if not started:
            p = occurred
            z = float(value) if value > 0 else 0.0
            started = True
            continue
        p = p + alpha * (occurred - p)
        if value > 0:
            z = z + beta * (float(value) - z)
    rate = max(p, 0.0) * max(z, 0.0)
    return _cap(np.full(horizon, rate), y)


def forecast_ets(y: np.ndarray, horizon: int) -> np.ndarray | None:
    y = _as_float(y)
    if len(y) < 14:
        return forecast_seasonal_naive(y, horizon)
    if float(np.std(y)) == 0:
        return np.full(horizon, max(float(y[-1]), 0.0))
    cleaned = _winsorize(y)
    seasonal = len(cleaned) >= 56 and has_weekly_seasonality(cleaned)
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if seasonal:
                model = ExponentialSmoothing(
                    cleaned,
                    trend="add",
                    seasonal="add",
                    seasonal_periods=_SEASON,
                    initialization_method="estimated",
                )
            else:
                model = ExponentialSmoothing(
                    cleaned,
                    trend="add",
                    seasonal=None,
                    initialization_method="estimated",
                )
            fitted = model.fit(optimized=True, use_brute=False)
            fc = np.asarray(fitted.forecast(horizon), dtype=float)
        return _cap(fc, y)
    except Exception:
        return None


def _feature_row(
    hist: np.ndarray,
    t: int,
    start_dow: int,
    sku_code: float,
    parent_code: float = 0.0,
) -> list[float]:
    day = start_dow + t
    return [
        float(hist[t - 1]),
        float(hist[t - 7]),
        float(hist[t - 14]),
        float(hist[t - 28]),
        float(np.mean(hist[t - 7:t])),
        float(np.mean(hist[t - 28:t])),
        float(day % 7),
        float((day // 30) % 12),
        float(sku_code),
        float(parent_code),
        float(np.mean(hist[:t])),
    ]


def _design(y: np.ndarray, end: int, sku_code: float, start_dow: int, parent_code: float = 0.0):
    rows = []
    targets = []
    for t in range(28, end):
        rows.append(_feature_row(y, t, start_dow, sku_code, parent_code))
        targets.append(float(y[t]))
    if not rows:
        return np.empty((0, 11)), np.empty((0,))
    return np.asarray(rows, dtype=float), np.asarray(targets, dtype=float)


def _new_hgb(min_samples_leaf: int):
    from sklearn.ensemble import HistGradientBoostingRegressor

    return HistGradientBoostingRegressor(
        max_iter=50,
        max_depth=3,
        learning_rate=0.08,
        min_samples_leaf=min_samples_leaf,
        l2_regularization=0.1,
    )


def _recursive_hgb(
    model,
    history: np.ndarray,
    horizon: int,
    start_dow: int,
    sku_code: float,
    parent_code: float = 0.0,
) -> np.ndarray:
    hist = list(_as_float(history))
    out = []
    for _ in range(horizon):
        t = len(hist)
        if t < 28:
            pred = float(np.mean(hist)) if hist else 0.0
        else:
            feat = np.asarray(
                [_feature_row(np.asarray(hist), t, start_dow, sku_code, parent_code)],
                dtype=float,
            )
            pred = float(model.predict(feat)[0])
        pred = max(0.0, pred)
        out.append(pred)
        hist.append(pred)
    return _cap(np.asarray(out, dtype=float), history)


def fit_hgb_sku(y: np.ndarray, start_dow: int = 0):
    y = _as_float(y)
    if len(y) < 60 or int(np.sum(y > 0)) < 12:
        return None
    X, target = _design(y, len(y), 0.0, start_dow)
    if len(target) < 30:
        return None
    model = _new_hgb(min_samples_leaf=5)
    model.fit(X, target)
    return model


def fit_hgb_global(
    series: dict[str, np.ndarray],
    end: int | None,
    codes: dict[str, float],
    start_dow: int,
    parent_codes: dict[str, float] | None = None,
):
    chunks_x = []
    chunks_y = []
    parent_codes = parent_codes or {}
    for sku, y in series.items():
        y = _as_float(y)
        stop = len(y) if end is None else end
        X, target = _design(y, stop, codes[sku], start_dow, parent_codes.get(sku, 0.0))
        if len(target):
            chunks_x.append(X)
            chunks_y.append(target)
    if not chunks_y:
        return None
    X = np.vstack(chunks_x)
    target = np.concatenate(chunks_y)
    if len(target) < 40:
        return None
    model = _new_hgb(min_samples_leaf=20)
    model.fit(X, target)
    return model


def _predict_model(
    model_name: str,
    y: np.ndarray,
    horizon: int,
    *,
    start_dow: int,
    sku_code: float,
    hgb_sku_model,
    hgb_global_model,
    parent_code: float = 0.0,
) -> np.ndarray | None:
    if model_name == "seasonal_naive":
        return forecast_seasonal_naive(y, horizon)
    if model_name == "ets":
        return forecast_ets(y, horizon)
    if model_name == "croston":
        return forecast_croston(y, horizon)
    if model_name == "sba":
        return forecast_sba(y, horizon)
    if model_name == "tsb":
        return forecast_tsb(y, horizon)
    if model_name == "hgb_sku":
        if hgb_sku_model is None:
            return None
        return _recursive_hgb(hgb_sku_model, y, horizon, start_dow, 0.0)
    if model_name == "hgb_global":
        if hgb_global_model is None:
            return None
        return _recursive_hgb(hgb_global_model, y, horizon, start_dow, sku_code, parent_code)
    raise KeyError(model_name)


def choose_origins(n: int, horizon: int, step: int, min_train: int) -> list[int]:
    if n < horizon + 40:
        return []
    start = min(min_train, n - horizon)
    start = max(start, 40)
    if start + horizon > n:
        return []
    origins = list(range(start, n - horizon + 1, step))
    if not origins:
        origins = [n - horizon]
    return origins[-3:]


def _score_from_errors(model: str, abs_errs: list[float], sq_errs: list[float], biases: list[float], scale: float) -> ModelScore:
    mae = float(np.mean(abs_errs))
    if scale > 1e-8:
        mase = mae / scale
    else:
        mase = 0.0 if mae < 1e-8 else 999.0
    return ModelScore(
        model=model,
        mase=float(mase),
        rmse=float(np.sqrt(np.mean(sq_errs))),
        bias=float(np.mean(biases)),
        n_origins=len(abs_errs),
    )


def _align(series: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    cleaned = {k: _as_float(v) for k, v in series.items()}
    if not cleaned:
        return {}
    width = max(len(v) for v in cleaned.values())
    out = {}
    for key, values in cleaned.items():
        if len(values) < width:
            values = np.pad(values, (width - len(values), 0))
        out[key] = values
    return out


def _align_mask(masks: dict[str, np.ndarray] | None, series: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    out = {}
    for sku, values in series.items():
        if not masks or sku not in masks:
            out[sku] = np.zeros(len(values), dtype=bool)
            continue
        mask = np.asarray(masks[sku], dtype=bool).reshape(-1)
        if len(mask) < len(values):
            mask = np.pad(mask, (len(values) - len(mask), 0), constant_values=False)
        out[sku] = mask[: len(values)]
    return out


def _align_uplift(uplift: dict[str, np.ndarray] | None, series: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    out = {}
    for sku, y in series.items():
        if uplift is None or sku not in uplift:
            out[sku] = np.ones(len(y))
            continue
        u = np.asarray(uplift[sku], dtype=float)
        if len(u) < len(y):
            u = np.pad(u, (len(y) - len(u), 0), constant_values=1.0)
        out[sku] = u[: len(y)]
    return out


def run_portfolio(
    series: dict[str, np.ndarray],
    *,
    horizon: int = 90,
    backtest_horizon: int = 28,
    step: int = 28,
    min_train: int = 120,
    start_dow: int = 0,
    uplift: dict[str, np.ndarray] | None = None,
    future_uplift: dict[str, np.ndarray] | None = None,
    parents: dict[str, str] | None = None,
    stockout: dict[str, np.ndarray] | None = None,
) -> PortfolioResult:
    """Backtest every model and forecast `horizon` days for each SKU."""
    series = _align({k: v for k, v in series.items() if len(_as_float(v)) > 0})
    uplift = _align_uplift(uplift, series)
    stockout = _align_mask(stockout, series)
    if not series:
        return PortfolioResult("seasonal_naive", {}, {}, 0.0, 0.0, 0, 0, {})

    n = len(next(iter(series.values())))
    origins = choose_origins(n, backtest_horizon, step, min_train)
    codes = {sku: float(i) for i, sku in enumerate(sorted(series))}
    parents = parents or {}
    parent_ids = sorted({parents.get(sku) or sku for sku in series})
    parent_codes = {sku: float(parent_ids.index(parents.get(sku) or sku)) for sku in series}

    # Residuals and errors collected per sku per model.
    bucket: dict[str, dict[str, list]] = {
        sku: {m: [] for m in ALL_MODELS} for sku in series
    }

    def _record(sku: str, model_name: str, actual: np.ndarray, pred: np.ndarray):
        resid = actual - pred
        bucket[sku][model_name].append(resid)

    for origin in origins:
        trained = {
            sku: prepare_training_series(
                raw[:origin], uplift[sku][:origin], start_dow, stockout[sku][:origin]
            )
            for sku, raw in series.items()
        }
        global_model = fit_hgb_global(trained, None, codes, start_dow, parent_codes)
        hier = hierarchical_forecast(trained, parents, backtest_horizon)
        for sku, raw in series.items():
            train = trained[sku]
            hold_uplift = uplift[sku][origin:origin + backtest_horizon]
            actual = raw[origin:origin + backtest_horizon]
            for name in SKU_MODELS:
                pred = _predict_model(
                    name, train, backtest_horizon,
                    start_dow=start_dow, sku_code=0.0,
                    hgb_sku_model=None, hgb_global_model=None,
                )
                if pred is None:
                    continue
                _record(sku, name, actual, pred * hold_uplift)
            if global_model is not None:
                pred = _predict_model(
                    GLOBAL_MODEL, train, backtest_horizon,
                    start_dow=start_dow, sku_code=codes[sku],
                    hgb_sku_model=None, hgb_global_model=global_model,
                    parent_code=parent_codes[sku],
                )
                if pred is not None:
                    _record(sku, GLOBAL_MODEL, actual, pred * hold_uplift)
            if sku in hier:
                _record(sku, HIERARCHICAL_MODEL, actual, hier[sku] * hold_uplift)

    scores: dict[str, dict[str, ModelScore]] = {}
    for sku, raw in series.items():
        scale = mase_scale(raw)
        scores[sku] = {}
        for name in ALL_MODELS:
            parts = bucket[sku][name]
            if not parts:
                continue
            abs_errs, sq_errs, biases = [], [], []
            for resid in parts:
                abs_errs.append(float(np.mean(np.abs(resid))))
                sq_errs.append(float(np.mean(resid ** 2)))
                biases.append(float(np.mean(-resid)))  # pred - actual = -(actual - pred)
            scores[sku][name] = _score_from_errors(name, abs_errs, sq_errs, biases, scale)

    weights = {sku: float(np.sum(y)) + 0.25 for sku, y in series.items()}
    global_mase: dict[str, float] = {}
    unweighted: dict[str, float] = {}
    for name in ALL_MODELS:
        weighted = []
        plain = []
        for sku, w in weights.items():
            sc = scores[sku].get(name)
            if sc is None or not np.isfinite(sc.mase):
                continue
            weighted.append(sc.mase * w)
            plain.append(sc.mase)
        if weighted:
            denom = sum(
                w for sku, w in weights.items()
                if name in scores[sku] and np.isfinite(scores[sku][name].mase)
            ) or 1.0
            global_mase[name] = float(sum(weighted) / denom)
            unweighted[name] = float(np.mean(plain))

    if global_mase:
        global_winner = min(global_mase, key=lambda name: global_mase[name])
    else:
        global_winner = "seasonal_naive"

    # Final fits on the full (promo-adjusted, stockout-imputed) history.
    trained_full = {
        sku: prepare_training_series(raw, uplift[sku], start_dow, stockout[sku])
        for sku, raw in series.items()
    }
    final_global = fit_hgb_global(trained_full, None, codes, start_dow, parent_codes)
    final_hier = hierarchical_forecast(trained_full, parents, horizon)
    skus: dict[str, SkuForecast] = {}
    per_sku_wins = 0
    global_wins = 0
    selected_weight = 0.0
    selected_acc = 0.0
    baseline_acc = 0.0

    for sku, raw in series.items():
        train = trained_full[sku]
        sku_scores = scores.get(sku, {})
        finite = {m: s for m, s in sku_scores.items() if np.isfinite(s.mase)}
        if not finite:
            chosen = "seasonal_naive"
            reason = "fallback"
        else:
            sku_best = min(finite, key=lambda m: (finite[m].mase, finite[m].rmse))
            global_score = finite.get(global_winner)
            if (
                global_score is not None
                and sku_best != global_winner
                and finite[sku_best].mase <= global_score.mase * 0.95
            ):
                chosen = sku_best
                reason = "per_sku"
            elif global_score is not None:
                chosen = global_winner
                reason = "global" if sku_best != global_winner else "per_sku"
            else:
                chosen = sku_best
                reason = "per_sku"
        if reason == "per_sku" and chosen != global_winner:
            per_sku_wins += 1
        else:
            global_wins += 1

        if chosen == HIERARCHICAL_MODEL and sku in final_hier:
            pred = final_hier[sku]
        else:
            pred = _predict_model(
                chosen, train, horizon,
                start_dow=start_dow,
                sku_code=codes[sku],
                hgb_sku_model=None,
                hgb_global_model=final_global,
                parent_code=parent_codes[sku],
            )
        if pred is None:
            pred = forecast_seasonal_naive(train, horizon)
            chosen = "seasonal_naive"
            reason = "fallback"
        future = None
        if future_uplift and sku in future_uplift:
            future = np.asarray(future_uplift[sku], dtype=float)
        if future is not None and len(future) >= horizon:
            pred = _cap(pred * future[:horizon], raw)
        elif future is not None and len(future) > 0:
            padded = np.pad(future, (0, horizon - len(future)), constant_values=1.0)
            pred = _cap(pred * padded[:horizon], raw)

        resid_parts = bucket[sku].get(chosen) or []
        if resid_parts:
            resid = np.concatenate(resid_parts)
        else:
            resid = np.array([])
        if len(resid) >= 20:
            q10, q90 = np.quantile(resid, [0.10, 0.90])
        else:
            sigma = float(np.std(resid)) if len(resid) else float(np.std(raw) if len(raw) else 1.0)
            if not np.isfinite(sigma):
                sigma = 1.0
            q10, q90 = -1.28155156554 * sigma, 1.28155156554 * sigma
        q_low = float(q10)
        q_high = float(q90)
        # Daily band, for charts. The summed range uses sqrt(horizon) instead.
        lower = np.minimum(pred, np.clip(pred + q_low, 0, None))
        upper = np.maximum(pred, pred + q_high)
        upper = np.maximum(upper, lower)

        chosen_score = sku_scores.get(chosen)
        mase = chosen_score.mase if chosen_score else float("nan")
        rmse = chosen_score.rmse if chosen_score else float("nan")
        skus[sku] = SkuForecast(
            sku=sku,
            model=chosen,
            selection=reason,
            point=pred,
            lower=lower,
            upper=upper,
            mase=float(mase) if np.isfinite(mase) else 999.0,
            rmse=float(rmse) if np.isfinite(rmse) else 0.0,
            intermittent=is_intermittent(raw),
            has_seasonality=has_weekly_seasonality(raw),
            q_low=q_low,
            q_high=q_high,
            scores=sku_scores,
        )
        w = weights[sku]
        selected_acc += (skus[sku].mase if np.isfinite(skus[sku].mase) else 0) * w
        selected_weight += w
        base = sku_scores.get("ets")
        if base is not None and np.isfinite(base.mase):
            baseline_acc += base.mase * w

    selected_mase = selected_acc / selected_weight if selected_weight else 0.0
    # Baseline uses the same weights. SKUs where ETS could not be scored
    # simply don't contribute, so divide by the weight we actually added.
    baseline_weight = 0.0
    baseline_acc = 0.0
    for sku, w in weights.items():
        base = scores[sku].get("ets")
        if base is not None and np.isfinite(base.mase):
            baseline_acc += base.mase * w
            baseline_weight += w
    baseline_mase = baseline_acc / baseline_weight if baseline_weight else selected_mase

    return PortfolioResult(
        global_winner=global_winner,
        global_mase=global_mase,
        unweighted_mase=unweighted,
        baseline_mase=float(baseline_mase),
        selected_mase=float(selected_mase),
        per_sku_wins=per_sku_wins,
        global_wins=global_wins,
        skus=skus,
    )
