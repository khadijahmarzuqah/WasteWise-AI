"""Inventory analytics: expiry levels, FEFO waste-risk estimate, overstock and
slow-mover detection. Pure functions (no Streamlit, no DB) so they are testable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from . import forecast as fc
from . import recommend

# Overstock needs cover to exceed the threshold by this factor (avoids noisy borderline flags)
OVERSTOCK_TOLERANCE = 1.25

LEVEL_LABELS = {
    "Expired": "⛔ Expired",
    "Critical": "🔴 Critical (≤3 days)",
    "Warning": "🟠 Warning (≤7 days)",
    "Watch": "🟡 Watch (≤15 days)",
    "OK": "🟢 OK",
    "No expiry": "⚪ No expiry",
}


def expiry_level(days) -> str:
    if days is None or pd.isna(days):
        return "No expiry"
    if days < 0:
        return "Expired"
    if days <= 3:
        return "Critical"
    if days <= 7:
        return "Warning"
    if days <= 15:
        return "Watch"
    return "OK"


@dataclass
class Analysis:
    today: date
    products: pd.DataFrame
    batches: pd.DataFrame
    forecasts: dict
    recs: list
    totals: dict
    sales: pd.DataFrame = field(default_factory=pd.DataFrame)


# ------------------------------------------------------------------- batches
def _build_batches(products, batches, forecasts, today) -> pd.DataFrame:
    cols = ["batch_id", "sku", "name", "category", "price", "cost", "quantity", "expiry_date",
            "days_to_expiry", "expiry_level", "expiry_label", "expected_sold", "units_at_risk",
            "risk_pct", "value_at_risk", "stock_value", "forecast_available"]
    if batches.empty or products.empty:
        return pd.DataFrame(columns=cols)
    b = batches.merge(products[["sku", "name", "category", "price", "cost"]], on="sku", how="inner")
    b = b[b["quantity"] > 0].copy()
    if b.empty:
        return pd.DataFrame(columns=cols)
    b["expiry"] = pd.to_datetime(b["expiry_date"], errors="coerce")
    b["days_to_expiry"] = (b["expiry"] - pd.Timestamp(today)).dt.days.astype(float)
    b["expiry_level"] = b["days_to_expiry"].map(expiry_level)
    b["expiry_label"] = b["expiry_level"].map(LEVEL_LABELS)
    b["stock_value"] = b["quantity"] * b["price"]

    exp_sold, at_risk, fc_ok = {}, {}, {}
    # FEFO: earliest-expiring batch is sold first; later batches only get the
    # demand that is left over.
    for sku, g in b.sort_values(["sku", "expiry"], na_position="last").groupby("sku"):
        res = forecasts.get(sku)
        have = res is not None and res.available
        sold_prior = 0.0
        for idx, r in g.iterrows():
            q, d = float(r["quantity"]), r["days_to_expiry"]
            fc_ok[idx] = have
            if pd.isna(d):                      # non-perishable / no expiry date
                exp_sold[idx], at_risk[idx] = np.nan, 0.0
            elif d < 0:                         # already expired: all of it is lost
                exp_sold[idx], at_risk[idx] = 0.0, q
            elif have:
                cum = fc.demand_over(res, int(d) + 1)      # today .. expiry date inclusive
                sold = min(q, max(0.0, cum - sold_prior))
                sold_prior += sold
                risk = float(np.round(q - sold))
                at_risk[idx], exp_sold[idx] = risk, q - risk
            else:                               # no reliable forecast -> unknown
                exp_sold[idx], at_risk[idx] = np.nan, np.nan
    b["forecast_available"] = pd.Series(fc_ok)
    b["expected_sold"] = pd.Series(exp_sold)
    b["units_at_risk"] = pd.Series(at_risk)
    b["risk_pct"] = b["units_at_risk"] / b["quantity"]
    b["value_at_risk"] = b["units_at_risk"] * b["price"]
    return b[cols].sort_values(["days_to_expiry", "sku"], na_position="last").reset_index(drop=True)


# ------------------------------------------------------------------ products
def _build_products(products, batches_df, sales, forecasts, settings) -> pd.DataFrame:
    if products.empty:
        return pd.DataFrame()
    rows = []
    sales = sales.copy()
    if len(sales):
        sales["sale_date"] = pd.to_datetime(sales["sale_date"])
        last_global = sales["sale_date"].max()
        recent = sales[sales["sale_date"] > last_global - pd.Timedelta(days=30)]
        recent_units = recent.groupby("sku")["units"].sum().to_dict()
    else:
        recent_units = {}
    stock = batches_df.groupby("sku")["quantity"].sum().to_dict() if len(batches_df) else {}
    slow_v = settings["slow_velocity"]
    cap = settings["overstock_cover_cap"]

    for p in products.itertuples(index=False):
        res = forecasts.get(p.sku)
        have = res is not None and res.available
        qty = int(stock.get(p.sku, 0))
        g = batches_df[batches_df["sku"] == p.sku] if len(batches_df) else batches_df
        gx = g[g["days_to_expiry"].notna()] if len(g) else g
        nearest = gx.loc[gx["days_to_expiry"].idxmin()] if len(gx) else None
        nearest_days = float(nearest["days_to_expiry"]) if nearest is not None else np.nan
        n_days = res.n_days if res is not None else 0
        vel = (recent_units.get(p.sku, 0) / min(30, n_days)) if n_days >= fc.MIN_DAYS else np.nan
        daily = res.daily_rate if have else np.nan
        shelf = p.shelf_life_days if pd.notna(p.shelf_life_days) else None
        threshold = max(3.0, min(cap, float(shelf))) if shelf else cap
        if have and qty > 0:
            cover = qty / daily if daily > 0 else float("inf")
        else:
            cover = np.nan
        overstock = bool(have and qty > 0 and cover > threshold * OVERSTOCK_TOLERANCE)
        slow = bool(qty > 0 and not np.isnan(vel) and vel < slow_v)
        at_risk = float(g["units_at_risk"].fillna(0).sum()) if len(g) else 0.0
        val_risk = float(g["value_at_risk"].fillna(0).sum()) if len(g) else 0.0
        n_expired = int((g["expiry_level"] == "Expired").sum()) if len(g) else 0
        level = expiry_level(nearest_days) if qty > 0 else "No expiry"
        if qty == 0:
            status = "⚪ Out of stock"
        elif level in ("Expired", "Critical", "Warning", "Watch"):
            status = LEVEL_LABELS[level]
        elif overstock:
            status = "🟣 Overstocked"
        elif slow:
            status = "🔵 Slow-moving"
        else:
            status = "🟢 Healthy"
        rows.append(dict(
            sku=p.sku, name=p.name, category=p.category, price=p.price,
            cost=p.cost if pd.notna(p.cost) else np.nan,
            shelf_life_days=shelf, reorder_qty=int(p.reorder_qty or 0), is_sample=int(p.is_sample),
            quantity=qty, stock_value=qty * p.price, n_batches=len(g),
            nearest_expiry=(nearest["expiry_date"] if nearest is not None else None),
            days_left=nearest_days, expiry_level=level, n_expired_batches=n_expired,
            velocity_30d=vel, forecast_daily=daily,
            forecast_14d=(daily * fc.HORIZON if have else np.nan),
            days_cover=cover, cover_threshold=threshold,
            method=res.method if res else fc.INSUFFICIENT,
            confidence=res.confidence if res else fc.INSUFFICIENT,
            history_days=n_days, overstock=overstock, slow=slow,
            units_at_risk=at_risk, value_at_risk=val_risk, status=status,
        ))
    return pd.DataFrame(rows)


def _totals(prod, bat) -> dict:
    if prod.empty:
        return dict(total_products=0, total_qty=0, stock_value=0.0, near_expiry=0, critical=0,
                    expired_batches=0, overstocked=0, slow=0, units_at_risk=0, value_at_risk=0.0,
                    risk_pct=0.0, no_forecast=0)
    live = prod[prod["quantity"] > 0]
    near = live[(live["days_left"] >= 0) & (live["days_left"] <= 15)]
    stock_value = float(prod["stock_value"].sum())
    var = float(prod["value_at_risk"].sum())
    return dict(
        total_products=int(len(prod)),
        total_qty=int(prod["quantity"].sum()),
        stock_value=stock_value,
        near_expiry=int(len(near)),
        critical=int(((live["days_left"] >= 0) & (live["days_left"] <= 3)).sum()),
        expired_batches=int((bat["expiry_level"] == "Expired").sum()) if len(bat) else 0,
        overstocked=int(prod["overstock"].sum()),
        slow=int(prod["slow"].sum()),
        units_at_risk=int(round(prod["units_at_risk"].sum())),
        value_at_risk=var,
        risk_pct=(var / stock_value) if stock_value > 0 else 0.0,
        no_forecast=int((prod["method"] == fc.INSUFFICIENT).sum()),
    )


def build_analysis(products, batches, sales, settings, today: date) -> Analysis:
    skus = list(products["sku"]) if len(products) else []
    forecasts = fc.forecast_all(sales, skus, today) if skus else {}
    bat = _build_batches(products, batches, forecasts, today)
    prod = _build_products(products, bat, sales, forecasts, settings)
    recs = recommend.generate(prod, bat, settings, today) if len(prod) else []
    return Analysis(today=today, products=prod, batches=bat, forecasts=forecasts, recs=recs,
                    totals=_totals(prod, bat), sales=sales)
