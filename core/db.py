"""SQLite persistence layer.

Tables: products, batches (expiry batches), sales, recommendations,
action_log (approval / rejection history) and settings.
Every write bumps `data_version`, which the app uses as a cache key.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime

import pandas as pd

from . import config
from .sample_data import generate_sample

SCHEMA = """
CREATE TABLE IF NOT EXISTS products(
    sku TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    price REAL NOT NULL CHECK(price >= 0),
    cost REAL,
    shelf_life_days INTEGER,
    reorder_qty INTEGER DEFAULT 0,
    is_sample INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS batches(
    batch_id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL REFERENCES products(sku) ON DELETE CASCADE,
    quantity INTEGER NOT NULL CHECK(quantity >= 0),
    expiry_date TEXT,
    received_date TEXT
);
CREATE TABLE IF NOT EXISTS sales(
    sale_date TEXT NOT NULL,
    sku TEXT NOT NULL,
    units INTEGER NOT NULL CHECK(units >= 0),
    PRIMARY KEY (sale_date, sku)
);
CREATE TABLE IF NOT EXISTS recommendations(
    rec_id INTEGER PRIMARY KEY AUTOINCREMENT,
    rec_key TEXT UNIQUE NOT NULL,
    sku TEXT NOT NULL,
    batch_id INTEGER,
    product_name TEXT,
    category TEXT,
    action_type TEXT NOT NULL,
    priority TEXT,
    discount_pct INTEGER,
    suggested_reorder_qty INTEGER,
    units_at_risk REAL,
    value_at_risk REAL,
    rationale TEXT,
    status TEXT NOT NULL DEFAULT 'Pending',
    created_at TEXT,
    decided_at TEXT,
    decision_note TEXT
);
CREATE TABLE IF NOT EXISTS action_log(
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    rec_id INTEGER,
    sku TEXT,
    product_name TEXT,
    action_type TEXT,
    decision TEXT NOT NULL,
    note TEXT,
    decided_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings(
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE INDEX IF NOT EXISTS idx_batches_sku ON batches(sku);
CREATE INDEX IF NOT EXISTS idx_sales_sku ON sales(sku);
"""


@contextmanager
def connect():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(config.DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _py(v):
    """Convert pandas/numpy scalars (and NaN) into plain Python values."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v.item() if hasattr(v, "item") else v


def _bump(conn) -> None:
    conn.execute(
        "INSERT INTO settings(key, value) VALUES('data_version', '1') "
        "ON CONFLICT(key) DO UPDATE SET value = CAST(value AS INTEGER) + 1"
    )


# --------------------------------------------------------------------- setup
def init_db() -> None:
    with connect() as c:
        c.executescript(SCHEMA)
        seeded = c.execute("SELECT value FROM settings WHERE key='seeded'").fetchone()
    if not seeded:
        seed_sample()


def get_version() -> int:
    with connect() as c:
        r = c.execute("SELECT value FROM settings WHERE key='data_version'").fetchone()
    return int(r["value"]) if r else 0


def seed_sample(today: date | None = None) -> None:
    """Replace ALL data with SYNTHETIC sample data (also clears action history)."""
    products, batches, sales = generate_sample(today)
    with connect() as c:
        for t in ("recommendations", "action_log", "sales", "batches", "products"):
            c.execute(f"DELETE FROM {t}")
        c.executemany(
            "INSERT INTO products(sku,name,category,price,cost,shelf_life_days,reorder_qty,is_sample) "
            "VALUES(?,?,?,?,?,?,?,1)",
            [(r.sku, r.name, r.category, r.price, r.cost, r.shelf_life_days, r.reorder_qty)
             for r in products.itertuples()])
        c.executemany(
            "INSERT INTO batches(sku,quantity,expiry_date,received_date) VALUES(?,?,?,?)",
            [(r.sku, r.quantity, r.expiry_date, r.received_date) for r in batches.itertuples()])
        c.executemany(
            "INSERT INTO sales(sale_date,sku,units) VALUES(?,?,?)",
            [(r.sale_date, r.sku, int(r.units)) for r in sales.itertuples()])
        c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('seeded','1')")
        _bump(c)


def clear_all_data() -> None:
    with connect() as c:
        for t in ("recommendations", "action_log", "sales", "batches", "products"):
            c.execute(f"DELETE FROM {t}")
        c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('seeded','1')")
        _bump(c)


# ------------------------------------------------------------------ settings
def get_settings() -> dict:
    out = dict(config.DEFAULT_SETTINGS)
    with connect() as c:
        for r in c.execute("SELECT key, value FROM settings"):
            if r["key"] in out:
                try:
                    out[r["key"]] = float(r["value"])
                except (TypeError, ValueError):
                    pass
    return out


def save_settings(values: dict) -> None:
    with connect() as c:
        for k, v in values.items():
            if k in config.DEFAULT_SETTINGS:
                c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (k, str(float(v))))


# --------------------------------------------------------------------- reads
def _read(sql: str, params=()) -> pd.DataFrame:
    with connect() as c:
        return pd.read_sql_query(sql, c, params=params)


def read_products() -> pd.DataFrame:
    return _read("SELECT * FROM products ORDER BY category, name")


def read_batches() -> pd.DataFrame:
    return _read("SELECT * FROM batches ORDER BY sku, expiry_date")


def read_sales() -> pd.DataFrame:
    return _read("SELECT sale_date, sku, units FROM sales")


# ------------------------------------------------------------ product CRUD
def sku_exists(sku: str) -> bool:
    with connect() as c:
        return c.execute("SELECT 1 FROM products WHERE sku=?", (sku,)).fetchone() is not None


def add_product(sku, name, category, price, cost=None, shelf_life_days=None, reorder_qty=0,
                quantity=None, expiry_date=None) -> None:
    sku = str(sku).strip()
    if not sku or not str(name).strip():
        raise ValueError("SKU and product name are required.")
    if sku_exists(sku):
        raise ValueError(f"SKU '{sku}' already exists.")
    with connect() as c:
        c.execute(
            "INSERT INTO products(sku,name,category,price,cost,shelf_life_days,reorder_qty,is_sample) "
            "VALUES(?,?,?,?,?,?,?,0)",
            (sku, str(name).strip(), category, float(price), _py(cost), _py(shelf_life_days),
             int(reorder_qty or 0)))
        if quantity is not None and int(quantity) > 0:
            c.execute("INSERT INTO batches(sku,quantity,expiry_date,received_date) VALUES(?,?,?,?)",
                      (sku, int(quantity), expiry_date, date.today().isoformat()))
        _bump(c)


def update_product(sku, name, category, price, cost, shelf_life_days, reorder_qty) -> None:
    with connect() as c:
        c.execute(
            "UPDATE products SET name=?, category=?, price=?, cost=?, shelf_life_days=?, reorder_qty=? "
            "WHERE sku=?",
            (str(name).strip(), category, float(price), _py(cost), _py(shelf_life_days),
             int(reorder_qty or 0), sku))
        _bump(c)


def delete_product(sku) -> None:
    """Delete a product with its batches and sales history."""
    with connect() as c:
        c.execute("DELETE FROM batches WHERE sku=?", (sku,))
        c.execute("DELETE FROM sales WHERE sku=?", (sku,))
        c.execute("DELETE FROM products WHERE sku=?", (sku,))
        _bump(c)


def add_batch(sku, quantity, expiry_date) -> None:
    with connect() as c:
        c.execute("INSERT INTO batches(sku,quantity,expiry_date,received_date) VALUES(?,?,?,?)",
                  (sku, int(quantity), expiry_date, date.today().isoformat()))
        _bump(c)


def update_batch(batch_id, quantity, expiry_date) -> None:
    with connect() as c:
        c.execute("UPDATE batches SET quantity=?, expiry_date=? WHERE batch_id=?",
                  (int(quantity), expiry_date, int(batch_id)))
        _bump(c)


def delete_batch(batch_id) -> None:
    with connect() as c:
        c.execute("DELETE FROM batches WHERE batch_id=?", (int(batch_id),))
        _bump(c)


# ------------------------------------------------------------------- imports
def import_inventory(df: pd.DataFrame, mode: str = "merge") -> dict:
    """Import a validated inventory frame (one row per batch).

    mode="replace": delete all products/batches first (sales for SKUs that no
                    longer exist are removed too).
    mode="merge":   upsert the products in the file and replace *their* batches
                    with the rows in the file; other products are untouched.
    """
    if df.empty:
        return dict(products=0, batches=0)
    prod_cols = ["name", "category", "price", "cost", "shelf_life_days", "reorder_qty"]
    for col in ("cost", "shelf_life_days", "reorder_qty"):
        if col not in df.columns:
            df = df.assign(**{col: None})
    # last non-empty value per SKU wins
    prods = df.groupby("sku", sort=False)[prod_cols].last().reset_index()

    with connect() as c:
        if mode == "replace":
            c.execute("DELETE FROM batches")
            c.execute("DELETE FROM products")
        for r in prods.itertuples(index=False):
            c.execute(
                "INSERT INTO products(sku,name,category,price,cost,shelf_life_days,reorder_qty,is_sample) "
                "VALUES(?,?,?,?,?,?,?,0) "
                "ON CONFLICT(sku) DO UPDATE SET name=excluded.name, category=excluded.category, "
                "price=excluded.price, cost=COALESCE(excluded.cost, products.cost), "
                "shelf_life_days=COALESCE(excluded.shelf_life_days, products.shelf_life_days), "
                "reorder_qty=COALESCE(excluded.reorder_qty, products.reorder_qty), is_sample=0",
                (r.sku, r.name, r.category, float(r.price), _py(r.cost),
                 None if _py(r.shelf_life_days) is None else int(r.shelf_life_days),
                 0 if _py(r.reorder_qty) is None else int(r.reorder_qty)))
        if mode != "replace":
            c.executemany("DELETE FROM batches WHERE sku=?", [(s,) for s in prods["sku"]])
        today = date.today().isoformat()
        c.executemany(
            "INSERT INTO batches(sku,quantity,expiry_date,received_date) VALUES(?,?,?,?)",
            [(r.sku, int(r.quantity), _py(r.expiry_date), today) for r in df.itertuples(index=False)])
        c.execute("DELETE FROM sales WHERE sku NOT IN (SELECT sku FROM products)")
        c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('seeded','1')")
        _bump(c)
    return dict(products=len(prods), batches=len(df))


def import_sales(df: pd.DataFrame, mode: str = "merge") -> dict:
    """Import validated sales (columns sale_date, sku, units)."""
    if df.empty:
        return dict(rows=0)
    with connect() as c:
        if mode == "replace":
            c.execute("DELETE FROM sales")
        c.executemany(
            "INSERT OR REPLACE INTO sales(sale_date,sku,units) VALUES(?,?,?)",
            [(r.sale_date, r.sku, int(r.units)) for r in df.itertuples(index=False)])
        _bump(c)
    return dict(rows=len(df))


# ----------------------------------------------------------- recommendations
def sync_recommendations(recs: list[dict]) -> None:
    """Insert new recommendations, refresh pending ones, drop stale pending
    ones. Approved / rejected records are never modified."""
    now = _now()
    with connect() as c:
        existing = {r["rec_key"]: r["status"]
                    for r in c.execute("SELECT rec_key, status FROM recommendations")}
        keys = set()
        for r in recs:
            keys.add(r["rec_key"])
            vals = (r["sku"], _py(r.get("batch_id")), r["product_name"], r["category"],
                    r["action_type"], r["priority"], _py(r.get("discount_pct")),
                    _py(r.get("suggested_reorder_qty")), _py(r.get("units_at_risk")),
                    _py(r.get("value_at_risk")), r["rationale"])
            st = existing.get(r["rec_key"])
            if st is None:
                c.execute(
                    "INSERT INTO recommendations(sku,batch_id,product_name,category,action_type,priority,"
                    "discount_pct,suggested_reorder_qty,units_at_risk,value_at_risk,rationale,"
                    "rec_key,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?, 'Pending', ?)",
                    vals + (r["rec_key"], now))
            elif st == "Pending":
                c.execute(
                    "UPDATE recommendations SET sku=?,batch_id=?,product_name=?,category=?,action_type=?,"
                    "priority=?,discount_pct=?,suggested_reorder_qty=?,units_at_risk=?,value_at_risk=?,"
                    "rationale=? WHERE rec_key=?", vals + (r["rec_key"],))
        for key, st in existing.items():
            if st == "Pending" and key not in keys:
                c.execute("DELETE FROM recommendations WHERE rec_key=?", (key,))


def read_recommendations(status: str | None = None) -> pd.DataFrame:
    if status:
        return _read("SELECT * FROM recommendations WHERE status=? ORDER BY "
                     "CASE priority WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END, "
                     "COALESCE(value_at_risk,0) DESC, rec_id", (status,))
    return _read("SELECT * FROM recommendations ORDER BY rec_id")


def decide(rec_id: int, decision: str, note: str = "") -> bool:
    """Record an approval / rejection. Returns False if not pending.
    This only stores the decision - it never changes prices or orders."""
    if decision not in ("Approved", "Rejected"):
        raise ValueError("decision must be 'Approved' or 'Rejected'")
    now = _now()
    with connect() as c:
        r = c.execute("SELECT * FROM recommendations WHERE rec_id=? AND status='Pending'",
                      (int(rec_id),)).fetchone()
        if r is None:
            return False
        c.execute("UPDATE recommendations SET status=?, decided_at=?, decision_note=? WHERE rec_id=?",
                  (decision, now, note.strip() or None, int(rec_id)))
        c.execute(
            "INSERT INTO action_log(rec_id,sku,product_name,action_type,decision,note,decided_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (r["rec_id"], r["sku"], r["product_name"], r["action_type"], decision,
             note.strip() or None, now))
    return True


def read_action_log() -> pd.DataFrame:
    return _read("SELECT l.decided_at, l.sku, l.product_name, l.action_type, l.decision, l.note, "
                 "r.rationale FROM action_log l LEFT JOIN recommendations r ON r.rec_id = l.rec_id "
                 "ORDER BY l.log_id DESC")


def clear_action_history() -> None:
    with connect() as c:
        c.execute("DELETE FROM action_log")
        c.execute("DELETE FROM recommendations WHERE status != 'Pending'")
