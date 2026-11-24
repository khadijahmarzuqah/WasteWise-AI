"""SYNTHETIC sample retail data for WasteWise AI.

Everything generated here is SAMPLE / SYNTHETIC DATA. It is not from a real
store. Expiry dates are generated relative to "today" so the demo always has a
realistic mix of fresh, near-expiry, overstocked and slow-moving products.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

# (sku, name, category, price, cost, shelf_life_days, base_units_per_day,
#  reorder_qty, history_days, explicit_batches or None)
# explicit_batches: list of (quantity, days_to_expiry)
_P = [
    # --- Milk
    ("MLK001", "Full Cream Milk 1L", "Milk", 68, 58, 7, 42, 120, 90, [(180, 2), (150, 6)]),
    ("MLK002", "Toned Milk 500ml", "Milk", 30, 26, 7, 55, 150, 90, None),
    ("MLK003", "Chocolate Milk 200ml", "Milk", 25, 19, 120, 14, 100, 90, None),
    ("MLK004", "Oat Milk 1L (new listing)", "Milk", 190, 150, 30, 3, 24, 6, [(60, 20)]),
    # --- Yogurt
    ("YOG001", "Curd 400g", "Yogurt", 40, 32, 10, 30, 90, 90, [(150, 3), (90, 9)]),
    ("YOG002", "Greek Yogurt 100g", "Yogurt", 55, 42, 21, 8, 40, 90, [(40, 8)]),
    ("YOG003", "Sweet Lassi 200ml", "Yogurt", 25, 18, 14, 18, 60, 90, None),
    ("YOG004", "Probiotic Shot 65ml (new listing)", "Yogurt", 15, 11, 21, 10, 60, 20, [(130, 12)]),
    # --- Bread
    ("BRD001", "White Bread 400g", "Bread", 45, 36, 4, 35, 60, 90, [(90, 1), (40, 3)]),
    ("BRD002", "Multigrain Bread 400g", "Bread", 60, 48, 5, 15, 30, 90, None),
    ("BRD003", "Burger Buns 4pk", "Bread", 40, 30, 4, 9, 20, 90, [(30, 2)]),
    # --- Biscuits
    ("BIS001", "Glucose Biscuits 120g", "Biscuits", 10, 8, 150, 60, 600, 90, [(3600, 110)]),
    ("BIS002", "Cream Biscuits 100g", "Biscuits", 30, 23, 150, 22, 240, 90, None),
    ("BIS003", "Digestive Biscuits 250g", "Biscuits", 55, 42, 180, 0.7, 48, 90, [(120, 120)]),
    # --- Juice
    ("JUC001", "Orange Juice 1L", "Juice", 110, 85, 90, 9, 48, 90, None),
    ("JUC002", "Mango Drink 200ml", "Juice", 20, 15, 120, 28, 300, 90, [(900, 80)]),
    ("JUC003", "Cold-Pressed Juice 250ml", "Juice", 90, 65, 5, 4, 12, 90, [(25, 3)]),
    ("JUC004", "Coconut Water 200ml", "Juice", 35, 26, 120, 0.7, 48, 90, [(90, 70)]),
    # --- Vegetables
    ("VEG001", "Tomato 1kg", "Vegetables", 40, 28, 6, 25, 80, 90, None),
    ("VEG002", "Potato 1kg", "Vegetables", 35, 24, 20, 30, 150, 90, None),
    ("VEG003", "Spinach Bunch", "Vegetables", 20, 13, 3, 12, 40, 90, [(40, 2)]),
    ("VEG004", "Capsicum 500g", "Vegetables", 45, 32, 7, 6, 25, 90, None),
    # --- Fruits
    ("FRU001", "Banana (dozen)", "Fruits", 60, 44, 5, 18, 50, 90, None),
    ("FRU002", "Apple 1kg", "Fruits", 180, 140, 20, 10, 40, 90, None),
    ("FRU003", "Papaya (medium)", "Fruits", 70, 50, 5, 5, 20, 90, [(35, 4)]),
    ("FRU004", "Grapes 500g", "Fruits", 90, 68, 7, 7, 25, 90, [(60, 6)]),
    # --- Snacks
    ("SNK001", "Potato Chips 52g", "Snacks", 20, 15, 120, 40, 500, 90, [(2400, 75)]),
    ("SNK002", "Namkeen Mixture 200g", "Snacks", 55, 40, 150, 12, 120, 90, [(600, 100)]),
    ("SNK003", "Salted Popcorn 90g", "Snacks", 40, 29, 150, 0.8, 48, 90, [(100, 110)]),
    ("SNK004", "Protein Bar 50g", "Snacks", 120, 90, 240, 1.5, 48, 90, None),
    # --- Other Grocery
    ("GRO001", "Basmati Rice 5kg", "Other Grocery", 520, 430, 365, 4, 24, 90, None),
    ("GRO002", "Sunflower Oil 1L", "Other Grocery", 150, 128, 270, 11, 60, 90, None),
    ("GRO003", "Instant Noodles 70g", "Other Grocery", 14, 10, 240, 45, 600, 90, [(2500, 150)]),
    ("GRO004", "Tea Powder 250g", "Other Grocery", 130, 100, 365, 6, 36, 90, None),
    ("GRO005", "Peanut Butter 340g", "Other Grocery", 210, 160, 270, 0.6, 24, 90, [(60, 200)]),
]

_DOW = np.array([0.90, 0.85, 0.90, 0.95, 1.10, 1.25, 1.15])  # Mon..Sun


def generate_sample(today: date | None = None, seed: int = 42):
    """Return (products, batches, sales) DataFrames of SYNTHETIC data."""
    today = today or date.today()
    rng = np.random.default_rng(seed)
    prod_rows, batch_rows, sales_rows = [], [], []

    for (sku, name, cat, price, cost, shelf, daily, reorder, hist, spec) in _P:
        prod_rows.append(dict(
            sku=sku, name=name, category=cat, price=float(price), cost=float(cost),
            shelf_life_days=int(shelf), reorder_qty=int(reorder),
        ))

        # ---- stock batches
        if spec is None:
            perishable = shelf <= 21
            if perishable:
                cover = rng.uniform(0.45, 0.8) * min(shelf, 14)
                days_left = int(rng.integers(max(4, int(shelf * 0.5)), shelf + 1))
            else:
                cover = rng.uniform(10, 22)
                days_left = int(rng.integers(int(shelf * 0.35), int(shelf * 0.9)))
            spec = [(max(5, int(round(daily * cover))), days_left)]
        for qty, dte in spec:
            batch_rows.append(dict(
                sku=sku, quantity=int(qty),
                expiry_date=(today + timedelta(days=int(dte))).isoformat(),
                received_date=(today - timedelta(days=max(0, shelf - int(dte)))).isoformat(),
            ))

        # ---- sales history (ends yesterday)
        trend = rng.uniform(-0.12, 0.12)
        for i in range(hist):
            d = today - timedelta(days=hist - i)
            lam = daily * _DOW[d.weekday()] * (1 + trend * (i / hist - 0.5))
            lam *= rng.gamma(shape=40, scale=1 / 40)  # mild day-to-day noise
            sales_rows.append(dict(sale_date=d.isoformat(), sku=sku, units=int(rng.poisson(max(lam, 0)))))

    return pd.DataFrame(prod_rows), pd.DataFrame(batch_rows), pd.DataFrame(sales_rows)


def sample_inventory_csv(today: date | None = None) -> pd.DataFrame:
    """Inventory CSV layout (one row per batch)."""
    p, b, _ = generate_sample(today)
    df = b.merge(p, on="sku")
    return df[["sku", "name", "category", "price", "cost", "quantity", "expiry_date",
               "shelf_life_days", "reorder_qty"]]


def sample_sales_csv(today: date | None = None) -> pd.DataFrame:
    _, _, s = generate_sample(today)
    return s.rename(columns={"units": "units_sold"})[["sale_date", "sku", "units_sold"]].rename(
        columns={"sale_date": "date"})


def template_inventory_csv() -> pd.DataFrame:
    t = date.today()
    return pd.DataFrame([
        ["MLK900", "Sample Milk 1L", "Milk", 68, 58, 120, (t + timedelta(days=5)).isoformat(), 7, 100],
        ["MLK900", "Sample Milk 1L", "Milk", 68, 58, 80, (t + timedelta(days=9)).isoformat(), 7, 100],
        ["BIS900", "Sample Biscuits 100g", "Biscuits", 30, 23, 300, (t + timedelta(days=120)).isoformat(), 150, 200],
    ], columns=["sku", "name", "category", "price", "cost", "quantity", "expiry_date",
                "shelf_life_days", "reorder_qty"])


def template_sales_csv() -> pd.DataFrame:
    t = date.today()
    rows = []
    for i in range(1, 4):
        d = (t - timedelta(days=i)).isoformat()
        rows += [[d, "MLK900", 40 + i], [d, "BIS900", 12 - i]]
    return pd.DataFrame(rows, columns=["date", "sku", "units_sold"])
