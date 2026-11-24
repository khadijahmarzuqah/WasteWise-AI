"""Central configuration for WasteWise AI."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("WASTEWISE_DB", BASE_DIR / "data" / "wastewise.db"))

APP_NAME = "WasteWise AI"
TAGLINE = "Predict Waste. Prevent Loss. Protect Resources."
CURRENCY = "₹"

CATEGORIES = [
    "Milk", "Yogurt", "Bread", "Biscuits", "Juice",
    "Vegetables", "Fruits", "Snacks", "Other Grocery",
]

# Expiry warning windows (days). Cumulative: "within 7 days" includes "within 3 days".
EXPIRY_WINDOWS = (3, 7, 15)

# User-editable thresholds (stored in the SQLite `settings` table).
DEFAULT_SETTINGS = {
    # Slow-moving: average units/day over the last 30 days below this value.
    "slow_velocity": 1.0,
    # Overstock: stock covers more days of forecast demand than
    # min(this cap, product shelf life).
    "overstock_cover_cap": 30.0,
    # When suggesting a reduced reorder, aim for this many days of cover.
    "target_cover_days": 14.0,
}

# Colour palette (white + soft green + dark green)
GREEN_DARK = "#14532D"
GREEN = "#1F7A4D"
GREEN_MID = "#4FA876"
GREEN_SOFT = "#BFE3CC"
GREEN_PALE = "#EAF6EE"
AMBER = "#E8A03A"
RED = "#D64545"
GREY = "#8A9A90"

# Navigation labels (single source of truth)
NAV_DASHBOARD = "📊  Dashboard"
NAV_INVENTORY = "📦  Inventory"
NAV_EXPIRY = "⏳  Expiry Monitor"
NAV_FORECAST = "📈  Demand Forecast"
NAV_ACTIONS = "✅  Action Centre"
NAV_DATA = "🗂️  Data Management"
NAV_REPORTS = "📑  Reports"
NAV_SETTINGS = "⚙️  Settings & About"
NAV_PAGES = [
    NAV_DASHBOARD, NAV_INVENTORY, NAV_EXPIRY, NAV_FORECAST,
    NAV_ACTIONS, NAV_DATA, NAV_REPORTS, NAV_SETTINGS,
]
