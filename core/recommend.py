"""Rule-based recommendation engine.

Every recommendation is produced by the fixed, documented rules below and
carries a plain-English rationale built from the product's actual numbers.
Nothing here changes prices or orders: staff must approve each suggestion in
the Action Centre, and approval only records the decision.
"""
from __future__ import annotations

import math

import pandas as pd

from .config import CURRENCY

RULES_MARKDOWN = """
**How suggestions are produced** (all rules are visible and editable in `core/recommend.py`):

| # | Condition | Suggestion | Priority |
|---|-----------|-----------|----------|
| 1 | A batch is already **expired** | Remove expired stock | High |
| 2 | Forecast says units **will not sell before expiry** and the batch expires in **≤ 3 days** | **20% discount** | High |
| 3 | …expires in **4–7 days** and **≥ 50%** of the batch is at risk | **20% discount** | Medium |
| 4 | …expires in **4–7 days** and **< 50%** is at risk | **10% discount** | Medium |
| 5 | …expires in **8–15 days** | **10% discount** | Medium |
| 6 | Batch expires in **≤ 7 days** but no discount is triggered (or no reliable forecast exists) | Prioritise: move to front of shelf (FEFO) | High if ≤ 3 days, else Medium |
| 7 | Stock covers **more than 1.25×** `min(overstock cap, shelf life)` days of forecast demand | Reduce next reorder (or skip it) | Medium if cover > 2× threshold, else Low |
| 8 | Sales velocity (last 30 days) **below the slow-moving threshold** | Monitor slow-moving product | Low |

**Units at risk** are estimated with FEFO (first-expiry-first-out): the earliest batch gets the forecast demand first,
later batches only get what is left. Products with **< 14 days** of sales history get **no forecast**, so rules 2–5 and 7
never fire for them – they only get rules 1, 6 and 8 where applicable.
Discount suggestions warn you if the discounted price would fall below unit cost.
"""


def _inr(x: float) -> str:
    return f"{CURRENCY}{x:,.0f}"


def _rec(key, b_or_p, action, priority, rationale, batch_id=None, discount=None,
         reorder=None, units=None, value=None) -> dict:
    return dict(
        rec_key=key, sku=b_or_p["sku"], batch_id=batch_id, product_name=b_or_p["name"],
        category=b_or_p["category"], action_type=action, priority=priority,
        discount_pct=discount, suggested_reorder_qty=reorder, units_at_risk=units,
        value_at_risk=value, rationale=rationale,
    )


def generate(prod: pd.DataFrame, bat: pd.DataFrame, settings: dict, today) -> list[dict]:
    recs: list[dict] = []
    iso = today.isocalendar()
    week = f"{iso[0]}W{iso[1]:02d}"
    pidx = prod.set_index("sku", drop=False)

    # ----- batch-level rules (expiry)
    for b in bat.itertuples(index=False):
        d = b.days_to_expiry
        if pd.isna(d):
            continue
        d = int(d)
        p = pidx.loc[b.sku]
        base = f"{b.sku}|{int(b.batch_id)}"
        bd = dict(sku=b.sku, name=b.name, category=b.category)
        q = int(b.quantity)

        if d < 0:
            recs.append(_rec(
                base + "|expired", bd, "Remove expired stock", "High",
                f"Batch #{int(b.batch_id)} ({q} units) expired {-d} day(s) ago on {b.expiry_date}. "
                f"Remove it from the shelf and record it as waste (value {_inr(q * b.price)}).",
                batch_id=int(b.batch_id), units=q, value=q * b.price))
            continue

        risk, known = b.units_at_risk, not pd.isna(b.units_at_risk)
        when = "today" if d == 0 else f"in {d} day(s)"
        if known and risk > 0 and d <= 15:
            share = risk / q
            pct = 20 if (d <= 3 or (d <= 7 and share >= 0.5)) else 10
            prio = "High" if d <= 3 else "Medium"
            conf = p["confidence"]
            new_price = b.price * (1 - pct / 100)
            margin = ""
            if pd.notna(b.cost):
                if new_price < b.cost:
                    margin = (f" ⚠ Discounted price {CURRENCY}{new_price:,.2f} is below unit cost "
                              f"{CURRENCY}{b.cost:,.2f}; consider a bundle or donation instead.")
                else:
                    margin = (f" Discounted price {CURRENCY}{new_price:,.2f} stays above unit cost "
                              f"{CURRENCY}{b.cost:,.2f}.")
            recs.append(_rec(
                base + "|discount", bd, f"Apply {pct}% discount", prio,
                f"Batch #{int(b.batch_id)} ({q} units) expires {when} ({b.expiry_date}). Forecast demand before "
                f"expiry is about {b.expected_sold:,.0f} units (forecast confidence: {conf}), so about "
                f"{risk:,.0f} units ({share:.0%}) may go unsold, worth {_inr(b.value_at_risk)}. "
                f"A {pct}% markdown can speed up sales.{margin}",
                batch_id=int(b.batch_id), discount=pct, units=risk, value=b.value_at_risk))
        elif d <= 7:
            if known:
                why = (f"Forecast suggests this batch should sell before expiry, but it is close to the date, so "
                       f"keep it at the front (FEFO).")
            else:
                why = ("There is not enough sales history to forecast demand for this product, so no discount "
                       "is suggested; review it manually.")
            recs.append(_rec(
                base + "|prioritise", bd, "Prioritise near-expiry stock", "High" if d <= 3 else "Medium",
                f"Batch #{int(b.batch_id)} ({q} units) expires {when} ({b.expiry_date}). {why}",
                batch_id=int(b.batch_id), units=None if not known else risk,
                value=None if not known else b.value_at_risk))

    # ----- product-level rules (stock level & velocity)
    target = settings["target_cover_days"]
    for p in prod.itertuples(index=False):
        pd_ = dict(sku=p.sku, name=p.name, category=p.category)
        if p.overstock:
            daily = p.forecast_daily
            needed = max(0, math.ceil(daily * target - p.quantity)) if daily > 0 else 0
            cur = int(p.reorder_qty)
            sugg = min(cur, needed) if cur > 0 else needed
            cover_txt = "more than 1 year" if p.days_cover == float("inf") or p.days_cover > 365 \
                else f"about {p.days_cover:,.0f} days"
            if sugg == 0:
                action = "Skip next reorder"
                what = "Skip the next reorder"
            else:
                action = "Reduce next reorder quantity"
                what = f"Reduce the next reorder from {cur} to {sugg} units" if cur > 0 else \
                    f"Limit the next reorder to {sugg} units"
            prio = "Medium" if (p.days_cover == float("inf") or p.days_cover > 2 * p.cover_threshold) else "Low"
            recs.append(_rec(
                f"{p.sku}|P|reorder|{week}", pd_, action, prio,
                f"Current stock of {p.quantity:,} units covers {cover_txt} of forecast demand "
                f"(~{daily:,.1f} units/day, confidence: {p.confidence}); the overstock threshold for this product is "
                f"{p.cover_threshold:,.0f} days (flagged above 1.25× that). {what} to aim for about {target:,.0f} days of cover.",
                reorder=sugg, units=None))
        if p.slow:
            recs.append(_rec(
                f"{p.sku}|P|monitor|{week}", pd_, "Monitor slow-moving product", "Low",
                f"Sales velocity over the last 30 days is {p.velocity_30d:,.2f} units/day, below the slow-moving "
                f"threshold of {settings['slow_velocity']:,.1f}. {p.quantity:,} units are in stock. "
                f"Review shelf placement, promotion, or whether to keep stocking it.",
                units=None))

    order = {"High": 0, "Medium": 1, "Low": 2}
    recs.sort(key=lambda r: (order[r["priority"]], -(r["value_at_risk"] or 0)))
    return recs
