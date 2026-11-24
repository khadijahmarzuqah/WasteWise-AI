# 🌿 WasteWise AI

**Predict Waste. Prevent Loss. Protect Resources.**

AI-assisted retail waste prediction and prevention for store managers. Built for Maatram HackForge 2026–27 (MH26-06, Software Track) by Team Pixel Panthers, JNN Institute of Engineering.

WasteWise AI forecasts demand, flags products that are close to expiry, overstocked or slow-moving, estimates the waste at risk, and suggests actions (discounts, smaller reorders, prioritising stock) for staff to **approve or reject**. It never changes real prices or orders.

> ⚠️ All bundled data is **SAMPLE / SYNTHETIC DATA** generated for demonstration. No real-store results are shown. Upload your own CSVs to use real data.

## Features

| Area | What it does |
|---|---|
| Dashboard | Total products, total stock, near-expiry, overstocked, slow-moving, estimated waste risk, forecast-vs-actual chart, category distribution, expiry buckets |
| Inventory | Search/filter, add, edit, delete products and stock batches (quantity, price, category, expiry) |
| Expiry Monitor | Batches expiring within 3 / 7 / 15 days and already expired, colour-coded warning levels, waste risk per batch |
| Demand Forecast | Per-product forecast (moving average vs. Ridge regression with weekday seasonality, chosen by back-test), confidence rating, stock vs forecast demand |
| Action Centre | Rule-based suggestions with plain-English reasons; approve / reject with a note; decisions and history stored in SQLite |
| Data Management | Upload inventory & sales CSVs with row-level validation, download templates and sample data, export CSV reports, reset data |
| Reports | Waste-risk summary, expiring, overstock, slow-moving and discount reports (all downloadable as CSV) |
| Settings | Adjust slow-moving / overstock thresholds (stored in the database) |

## How the "AI" works (and what it doesn't claim)

1. **Forecast** – per SKU, daily sales are modelled with a flat 14-day moving average and a scikit-learn Ridge regression (weekday dummies + trend). The better one on a hold-out back-test is used.
2. **Honesty about data** – under 14 days of history → *no forecast*; 14–27 days → rough moving average, confidence *Low*; 28+ days → back-tested, confidence from hold-out error (never *High* below 60 days).
3. **Waste risk** – units forecast not to sell before each batch's expiry, assuming first-expiry-first-out selling.
4. **Recommendations** – a fixed, documented rule table (see the *How suggestions work* tab in the app, or `core/recommend.py`). Every suggestion shows the numbers behind it.

Not modelled: promotions, festivals, weather, stock-outs, price elasticity.

## Project structure

```
app.py                 Streamlit entry point (navigation, caching, routing)
core/
  config.py            constants, palette, default thresholds
  db.py                SQLite schema + all reads/writes
  sample_data.py       SYNTHETIC data generator + CSV templates
  validation.py        CSV reading and row-level validation
  forecast.py          demand forecasting + back-testing
  analysis.py          expiry levels, FEFO waste risk, overstock, slow-movers
  recommend.py         transparent recommendation rules
  charts.py, ui.py     Plotly figures, CSS theme, helpers
views/                 one module per page
sample_data/           sample + template CSVs (SYNTHETIC)
tests/                 pytest suite (core logic + UI smoke test)
.streamlit/config.toml theme + server settings
```

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Open http://localhost:8501. On first start the app creates `data/wastewise.db` and loads the sample data. Data persists in that file across restarts. To start fresh, use **Data Management → Reset** or delete the file.

## CSV formats

**Inventory** (one row per stock batch) – required: `sku, name, category, price, quantity, expiry_date` (`YYYY-MM-DD`, may be blank for non-perishables). Optional: `cost, shelf_life_days, reorder_qty`.

**Sales** – required: `date` (`YYYY-MM-DD`), `sku`, `units_sold`. Every SKU must exist in inventory. Days with no row count as zero sales, so include every trading day.

Templates and full sample files are in `sample_data/` and on the **Data Management** page. Invalid rows are listed with row numbers and reasons; you can import the valid rows only.

## Tests

```bash
pip install pytest
python -m pytest -q
```

`tests/test_core.py` covers the database, validation, forecasting, analysis, recommendations and approval workflow. `tests/test_ui_smoke.py` executes every page's code against lightweight stand-ins for Streamlit/Plotly (it does not test Streamlit rendering itself).

## Deploy on Streamlit Community Cloud (free)

1. Push this folder to a GitHub repository (see below).
2. Go to https://share.streamlit.io and sign in with GitHub, authorising Streamlit to read your repo.
3. Click **Create app → Deploy a public app from GitHub**, choose the repository, branch `main`, and main file `app.py`.
4. (Advanced settings) pick Python 3.11 or 3.12. Click **Deploy**.

```bash
git init -b main && git add . && git commit -m "WasteWise AI"
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

**Good to know about the free host**
- The container's disk is **ephemeral**: the SQLite file is reset when the app is rebuilt, rebooted or wakes from sleep, so the demo returns to fresh sample data. Locally the database is permanent.
- A public demo shares **one database for all visitors**. Anyone can edit or approve items; use *Reset* to restore the sample data. Don't upload confidential data to a public demo.
- Sample expiry dates are relative to the day the data was generated; *Data Management → Reset → Reload sample data* refreshes them.

For permanent hosted data, point `WASTEWISE_DB` at a persistent volume or swap `core/db.py` for a hosted database.

## Licence

Hackathon project. Libraries used: Streamlit, pandas, NumPy, scikit-learn, Plotly (all open source).
