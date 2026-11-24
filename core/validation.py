"""CSV reading and validation with row-level, human-readable error messages."""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import pandas as pd

from . import config

MAX_BYTES = 10 * 1024 * 1024

INVENTORY_REQUIRED = ["sku", "name", "category", "price", "quantity", "expiry_date"]
INVENTORY_OPTIONAL = ["cost", "shelf_life_days", "reorder_qty"]
SALES_REQUIRED = ["date", "sku", "units_sold"]

_ALIASES = {
    "product_name": "name", "product": "name", "item": "name", "item_name": "name",
    "product_id": "sku", "item_code": "sku", "sku_id": "sku",
    "stock": "quantity", "qty": "quantity", "stock_quantity": "quantity", "quantity_on_hand": "quantity",
    "unit_price": "price", "selling_price": "price", "mrp": "price",
    "unit_cost": "cost", "cost_price": "cost",
    "expiry": "expiry_date", "expiration_date": "expiry_date", "exp_date": "expiry_date", "best_before": "expiry_date",
    "shelf_life": "shelf_life_days", "reorder_quantity": "reorder_qty",
    "sale_date": "date", "sales_date": "date",
    "units": "units_sold", "quantity_sold": "units_sold", "qty_sold": "units_sold", "sold": "units_sold",
}


@dataclass
class ValidationResult:
    fatal: str | None = None                 # file-level problem (cannot import)
    clean: pd.DataFrame = field(default_factory=pd.DataFrame)   # valid rows only
    row_errors: list = field(default_factory=list)              # [(row_number, message)]
    warnings: list = field(default_factory=list)
    n_rows: int = 0

    @property
    def n_valid(self) -> int:
        return len(self.clean)

    @property
    def ok(self) -> bool:
        return self.fatal is None and not self.row_errors and self.n_valid > 0


# --------------------------------------------------------------------- reading
def read_csv(source) -> tuple[pd.DataFrame | None, str | None]:
    """Read an uploaded file (Streamlit UploadedFile, bytes or path-like) as strings."""
    try:
        if isinstance(source, (bytes, bytearray)):
            raw = bytes(source)
        elif hasattr(source, "getvalue"):
            raw = source.getvalue()
        elif hasattr(source, "read"):
            raw = source.read()
        else:
            with open(source, "rb") as f:
                raw = f.read()
    except Exception as e:  # pragma: no cover
        return None, f"Could not read the file: {e}"
    if len(raw) > MAX_BYTES:
        return None, "File is larger than 10 MB. Please upload a smaller file."
    if not raw.strip():
        return None, "The file is empty."
    text = None
    for enc in ("utf-8-sig", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    try:
        df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False, skipinitialspace=True)
    except pd.errors.EmptyDataError:
        return None, "The file is empty."
    except Exception as e:
        return None, f"This does not look like a valid CSV file ({e})."
    return df, None


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    cols = []
    for c in df.columns:
        n = re.sub(r"[^a-z0-9]+", "_", str(c).strip().lower()).strip("_")
        cols.append(_ALIASES.get(n, n))
    df = df.copy()
    df.columns = cols
    return df


def _check_columns(df, required):
    missing = [c for c in required if c not in df.columns]
    if missing:
        return ("Missing required column(s): " + ", ".join(missing) +
                ". Columns found: " + (", ".join(df.columns) or "none") +
                ". Download the template to see the expected format.")
    if df.columns.duplicated().any():
        dup = sorted(set(df.columns[df.columns.duplicated()]))
        return "Duplicate column(s) after normalising names: " + ", ".join(dup)
    return None


class _Flags:
    def __init__(self):
        self.errs: dict = {}

    def flag(self, mask, msg):
        for i in mask[mask].index:
            self.errs.setdefault(i, []).append(msg)


def _opt_number(df, col, flags, label, minimum, integer=False, strictly_positive=False):
    """Validate an optional numeric column; returns a numeric Series (NaN = blank)."""
    if col not in df.columns:
        return pd.Series(float("nan"), index=df.index)
    s = df[col].str.strip()
    blank = s == ""
    num = pd.to_numeric(s.where(~blank), errors="coerce")
    bad = ~blank & (num.isna() | (num <= minimum if strictly_positive else num < minimum))
    if integer:
        bad |= ~blank & num.notna() & (num % 1 != 0)
    kind = "a whole number" if integer else "a number"
    cmp_ = f"greater than {minimum}" if strictly_positive else f"at least {minimum}"
    flags.flag(bad, f"{label} must be {kind} {cmp_} (or blank)")
    return num


def _finish(df, flags, clean_cols, warnings, n_rows):
    valid = ~df.index.isin(list(flags.errs))
    row_errors = [(int(i) + 2, "; ".join(m)) for i, m in sorted(flags.errs.items())]
    return ValidationResult(clean=df.loc[valid, clean_cols].reset_index(drop=True),
                            row_errors=row_errors, warnings=warnings, n_rows=n_rows)


# ------------------------------------------------------------------- inventory
def validate_inventory(raw: pd.DataFrame) -> ValidationResult:
    df = _normalise_columns(raw)
    err = _check_columns(df, INVENTORY_REQUIRED)
    if err:
        return ValidationResult(fatal=err)
    if len(df) == 0:
        return ValidationResult(fatal="The file has headers but no data rows.")
    for c in df.columns:
        df[c] = df[c].astype(str).str.strip()

    flags, warns = _Flags(), []
    flags.flag(df["sku"] == "", "sku is blank")
    flags.flag(df["name"] == "", "name is blank")
    flags.flag(df["category"] == "", "category is blank")

    price = pd.to_numeric(df["price"], errors="coerce")
    flags.flag(price.isna() | (price <= 0), "price must be a number greater than 0")
    qty = pd.to_numeric(df["quantity"], errors="coerce")
    flags.flag(qty.isna() | (qty < 0) | (qty % 1 != 0), "quantity must be a whole number, 0 or more")

    exp_s = df["expiry_date"]
    blank_exp = exp_s == ""
    exp = pd.to_datetime(exp_s.where(~blank_exp), format="%Y-%m-%d", errors="coerce")
    flags.flag(~blank_exp & exp.isna(), "expiry_date must be YYYY-MM-DD (e.g. 2026-12-31) or blank")

    cost = _opt_number(df, "cost", flags, "cost", 0)
    shelf = _opt_number(df, "shelf_life_days", flags, "shelf_life_days", 0, integer=True, strictly_positive=True)
    reorder = _opt_number(df, "reorder_qty", flags, "reorder_qty", 0, integer=True)

    # ---- warnings (do not block import)
    today = pd.Timestamp.today().normalize()
    n_expired = int((exp.notna() & (exp < today)).sum())
    if n_expired:
        warns.append(f"{n_expired} row(s) have an expiry date in the past (already expired stock).")
    n_nocost = int((cost > price).sum())
    if n_nocost:
        warns.append(f"{n_nocost} row(s) have cost higher than price.")
    n_noexp = int(blank_exp.sum())
    if n_noexp:
        warns.append(f"{n_noexp} row(s) have no expiry date; they are treated as non-perishable "
                     "and excluded from expiry/waste-risk checks.")
    for col in ("name", "price"):
        conflict = df.groupby("sku")[col].nunique()
        conflict = conflict[conflict > 1]
        if len(conflict):
            warns.append(f"SKU(s) with different {col} values across rows (the last row is used): "
                         + ", ".join(list(conflict.index[:5])) + ("…" if len(conflict) > 5 else ""))
    dup = df.assign(_e=exp_s).duplicated(subset=["sku", "_e"], keep=False) & ~(df["sku"] == "")
    if dup.any():
        warns.append(f"{int(dup.sum())} row(s) share the same SKU and expiry date; they are imported as separate batches.")
    known = {c.lower(): c for c in config.CATEGORIES}
    cat = df["category"].map(lambda v: known.get(v.lower(), v))
    unknown = sorted(set(cat) - set(config.CATEGORIES) - {""})
    if unknown:
        warns.append("Custom categories found (allowed): " + ", ".join(unknown[:6]))

    clean = pd.DataFrame({
        "sku": df["sku"], "name": df["name"], "category": cat, "price": price,
        "quantity": qty, "expiry_date": exp_s.where(~blank_exp, None),
        "cost": cost, "shelf_life_days": shelf, "reorder_qty": reorder,
    })
    res = _finish(clean, flags, list(clean.columns), warns, len(df))
    if len(res.clean):
        res.clean["quantity"] = res.clean["quantity"].astype(int)
    return res


# ----------------------------------------------------------------------- sales
def validate_sales(raw: pd.DataFrame, known_skus) -> ValidationResult:
    df = _normalise_columns(raw)
    err = _check_columns(df, SALES_REQUIRED)
    if err:
        return ValidationResult(fatal=err)
    if len(df) == 0:
        return ValidationResult(fatal="The file has headers but no data rows.")
    for c in df.columns:
        df[c] = df[c].astype(str).str.strip()

    known = set(known_skus)
    flags, warns = _Flags(), []
    if not known:
        return ValidationResult(fatal="There are no products yet. Upload or add inventory first, "
                                      "because every sales row must refer to an existing SKU.")
    dt = pd.to_datetime(df["date"], format="%Y-%m-%d", errors="coerce")
    flags.flag(dt.isna(), "date must be YYYY-MM-DD (e.g. 2026-11-24)")
    units = pd.to_numeric(df["units_sold"], errors="coerce")
    flags.flag(units.isna() | (units < 0) | (units % 1 != 0), "units_sold must be a whole number, 0 or more")
    flags.flag(df["sku"] == "", "sku is blank")
    unknown = (df["sku"] != "") & ~df["sku"].isin(known)
    flags.flag(unknown, "unknown SKU (not in inventory - add the product first)")

    today = pd.Timestamp.today().normalize()
    fut = int((dt > today).sum())
    if fut:
        warns.append(f"{fut} row(s) have a date in the future.")

    clean = pd.DataFrame({"sale_date": dt.dt.strftime("%Y-%m-%d"), "sku": df["sku"], "units": units})
    res = _finish(clean, flags, list(clean.columns), warns, len(df))
    if len(res.clean):
        before = len(res.clean)
        res.clean["units"] = res.clean["units"].astype(int)
        res.clean = res.clean.groupby(["sale_date", "sku"], as_index=False)["units"].sum()
        if len(res.clean) < before:
            res.warnings.append(f"{before - len(res.clean)} duplicate (date, SKU) row(s) were combined by summing units.")
    return res
