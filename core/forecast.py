"""Transparent demand forecasting.

Per SKU we build a daily sales series (days without a row count as 0 sales) and
choose between two honest candidates using a hold-out back-test:

  * Baseline: flat 14-day moving average
  * Ridge regression on weekday dummies + linear trend (scikit-learn)

The Ridge model is only used if it beats the baseline on the hold-out window.
With little history we do NOT pretend to forecast:

  * < 14 days of history  -> "Insufficient data" (no forecast produced)
  * 14-27 days            -> moving average, confidence "Low", no back-test
  * >= 28 days            -> back-tested; confidence from hold-out WAPE
                             (capped at "Medium" below 60 days of history)
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge

HORIZON = 14
MIN_DAYS = 14
BACKTEST_MIN_DAYS = 28

INSUFFICIENT = "Insufficient data"


@dataclass
class ForecastResult:
    sku: str
    method: str
    confidence: str
    n_days: int
    daily_rate: float = float("nan")      # mean forecast units/day over the horizon
    wape: float = float("nan")            # hold-out weighted absolute % error
    mae: float = float("nan")             # hold-out MAE of chosen method
    baseline_mae: float = float("nan")    # hold-out MAE of moving average
    history: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))
    future: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=["date", "forecast"]))
    backtest: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=["date", "actual", "predicted"]))
    note: str = ""

    @property
    def available(self) -> bool:
        return self.method != INSUFFICIENT


def _daily_series(g: pd.DataFrame) -> pd.Series:
    s = g.groupby("sale_date")["units"].sum().sort_index()
    idx = pd.date_range(s.index.min(), s.index.max(), freq="D")
    return s.reindex(idx, fill_value=0).astype(float)


def _design(dates: pd.DatetimeIndex, t0: pd.Timestamp) -> np.ndarray:
    dates = pd.DatetimeIndex(dates)
    dow = np.eye(7)[dates.dayofweek.to_numpy()]
    t = ((dates - t0).days.to_numpy() / 30.0)[:, None]
    return np.hstack([dow, t])


def _ridge_predict(train: pd.Series, dates) -> np.ndarray:
    train = train.iloc[-90:]
    t0 = train.index[0]
    model = Ridge(alpha=1.0, fit_intercept=False).fit(_design(train.index, t0), train.to_numpy())
    pred = model.predict(_design(dates, t0))
    cap = max(3.0 * float(train.tail(28).mean()), 1.0)       # guard against runaway trends
    return np.clip(pred, 0.0, cap)


def _ma_predict(train: pd.Series, dates) -> np.ndarray:
    return np.full(len(dates), float(train.tail(14).mean()))


def forecast_sku(sku: str, g: pd.DataFrame, today, horizon: int = HORIZON) -> ForecastResult:
    """g: DataFrame with columns sale_date (datetime64) and units for ONE sku."""
    today = pd.Timestamp(today).normalize()
    if g is None or len(g) == 0:
        return ForecastResult(sku, INSUFFICIENT, INSUFFICIENT, 0,
                              note="No sales history for this product.")
    s = _daily_series(g)
    n = len(s)
    if n < MIN_DAYS:
        return ForecastResult(sku, INSUFFICIENT, INSUFFICIENT, n, history=s,
                              note=f"Only {n} day(s) of sales history; at least {MIN_DAYS} are needed "
                                   "for a forecast. No prediction is shown.")
    fdates = pd.date_range(today, periods=horizon, freq="D")

    backtest = pd.DataFrame(columns=["date", "actual", "predicted"])
    wape = mae = base_mae = float("nan")

    if n < BACKTEST_MIN_DAYS:
        method, conf = "14-day moving average", "Low"
        pred = _ma_predict(s, fdates)
        note = (f"Only {n} days of history: a simple moving average is used and it could not be "
                "back-tested. Treat as a rough guide.")
    else:
        h = 14 if n >= 42 else 7
        train, test = s.iloc[:-h], s.iloc[-h:]
        p_ridge, p_ma = _ridge_predict(train, test.index), _ma_predict(train, test.index)
        mae_r = float(np.mean(np.abs(test.to_numpy() - p_ridge)))
        mae_b = float(np.mean(np.abs(test.to_numpy() - p_ma)))
        use_ridge = mae_r < 0.98 * mae_b
        p_best = p_ridge if use_ridge else p_ma
        mae, base_mae = (mae_r if use_ridge else mae_b), mae_b
        total = float(test.sum())
        wape = float(np.abs(test.to_numpy() - p_best).sum() / total) if total > 0 else float("nan")
        backtest = pd.DataFrame({"date": test.index, "actual": test.to_numpy(), "predicted": p_best})
        if use_ridge:
            method, pred = "Weekday-aware Ridge regression", _ridge_predict(s, fdates)
        else:
            method, pred = "14-day moving average", _ma_predict(s, fdates)
        if np.isnan(wape):
            conf = "Low"
        elif wape < 0.25:
            conf = "High"
        elif wape < 0.45:
            conf = "Medium"
        else:
            conf = "Low"
        if n < 60 and conf == "High":
            conf = "Medium"
        wape_txt = "n/a" if np.isnan(wape) else f"{wape:.0%}"
        note = (f"Back-tested on the last {h} days: error (WAPE) {wape_txt}; "
                f"{'Ridge beat' if use_ridge else 'moving average was at least as good as'} the baseline.")

    return ForecastResult(
        sku=sku, method=method, confidence=conf, n_days=n, daily_rate=float(np.mean(pred)),
        wape=wape, mae=mae, baseline_mae=base_mae, history=s,
        future=pd.DataFrame({"date": fdates, "forecast": pred}), backtest=backtest, note=note)


def forecast_all(sales: pd.DataFrame, skus, today) -> dict:
    sales = sales.copy()
    sales["sale_date"] = pd.to_datetime(sales["sale_date"])
    groups = {k: v for k, v in sales.groupby("sku")}
    return {sku: forecast_sku(sku, groups.get(sku), today) for sku in skus}


def demand_over(result: ForecastResult, days: int) -> float:
    """Expected units sold over the next `days` days (NaN if no forecast).
    Beyond the 14-day horizon the last 7 forecast days are repeated."""
    if result is None or not result.available:
        return float("nan")
    if days <= 0:
        return 0.0
    f = result.future["forecast"].to_numpy()
    if days <= len(f):
        return float(f[:days].sum())
    return float(f.sum() + np.resize(f[-7:], days - len(f)).sum())


def forecast_vs_actual(forecasts: dict, skus=None, lookback: int = 28) -> tuple[pd.DataFrame, int]:
    """Long frame (date, series, units) for charting + number of SKUs included.

    Aggregate view (skus=None) only includes SKUs that were back-tested, so the
    back-test line and the actual line are comparable. A single-SKU view shows
    whatever exists for that SKU.
    """
    if skus is None:
        use = [r for r in forecasts.values() if r.available and len(r.backtest)]
        bt_days = 7
    else:
        use = [forecasts[s] for s in skus if s in forecasts and forecasts[s].available]
        bt_days = 14
    if not use:
        return pd.DataFrame(columns=["date", "series", "units"]), 0

    actual = pd.concat([r.history for r in use], axis=1).fillna(0).sum(axis=1)
    actual = actual.iloc[-lookback:]
    parts = [pd.DataFrame({"date": actual.index, "series": "Actual sales", "units": actual.to_numpy()})]
    bts = [r.backtest.tail(bt_days).set_index("date")["predicted"] for r in use if len(r.backtest)]
    if bts:
        bt = pd.concat(bts, axis=1).sum(axis=1)
        parts.append(pd.DataFrame({"date": bt.index, "series": "Back-test prediction", "units": bt.to_numpy()}))
    fut = pd.concat([r.future.set_index("date")["forecast"] for r in use], axis=1).sum(axis=1)
    parts.append(pd.DataFrame({"date": fut.index, "series": "Forecast (next 14 days)", "units": fut.to_numpy()}))
    return pd.concat(parts, ignore_index=True), len(use)
