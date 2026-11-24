import pandas as pd
import streamlit as st

from core import charts, ui


def _dl(df, name):
    st.download_button("⬇️ Download CSV", ui.csv_bytes(df), f"{name}.csv", "text/csv", key=f"dl_{name}")


def render(ctx):
    A, t = ctx.analysis, ctx.analysis.totals
    ui.page_title("Reports & Analytics", "Waste-risk, expiry, overstock, slow-mover and discount reports. Every table can be exported.")
    ui.sample_banner(A.products)
    if A.products.empty:
        ui.empty_state("No data", "Add or upload inventory to generate reports.")
        return
    P, B = A.products, A.batches

    tabs = st.tabs(["Waste-risk summary", "Expiring products", "Overstock", "Slow-moving", "Discount recommendations"])

    with tabs[0]:
        ui.stat_cards([
            dict(label="Est. waste value", value=ui.inr(t["value_at_risk"]), sub=f'{t["risk_pct"]:.1%} of stock value', tone="danger"),
            dict(label="Units at risk", value=f'{t["units_at_risk"]:,}', sub="forecast not to sell before expiry", tone="warn"),
            dict(label="Expired batches", value=t["expired_batches"], sub="remove now", tone="danger" if t["expired_batches"] else ""),
            dict(label="No forecast", value=t["no_forecast"], sub="products with < 14 days of sales", tone="info"),
        ])
        cat = P.groupby("category").agg(products=("sku", "count"), stock_units=("quantity", "sum"),
                                         stock_value=("stock_value", "sum"), units_at_risk=("units_at_risk", "sum"),
                                         value_at_risk=("value_at_risk", "sum")).reset_index()
        cat["risk_share"] = (cat["value_at_risk"] / cat["stock_value"].replace(0, pd.NA) * 100).astype(float).fillna(0)
        cat = cat.sort_values("value_at_risk", ascending=False).rename(columns={
            "category": "Category", "products": "Products", "stock_units": "Stock units", "stock_value": "Stock value",
            "units_at_risk": "Units at risk", "value_at_risk": "Value at risk", "risk_share": "Stock value at risk (%)"})
        ui.table(cat, {"Stock value": ui.money_col("Stock value"), "Value at risk": ui.money_col("Value at risk"),
                       "Stock value at risk (%)": st.column_config.NumberColumn("Stock value at risk (%)", format="%.2f")})
        _dl(cat, "waste_risk_summary")
        if B["value_at_risk"].fillna(0).sum() > 0:
            with st.container(border=True):
                st.plotly_chart(charts.risk_by_category(B), use_container_width=True)
        st.caption("Waste risk is an estimate (retail value of units the forecast says will not sell before expiry). "
                   "Products without enough history are excluded from the estimate, not assumed to be safe.")

    with tabs[1]:
        d = B["days_to_expiry"]
        sel = st.radio("Window", ["Expired", "Within 3 days", "Within 7 days", "Within 15 days"], index=3, horizontal=True, key="rep_win")
        if sel == "Expired":
            df = B[d < 0]
        else:
            n = int(sel.split()[1])
            df = B[(d >= 0) & (d <= n)]
        rep = df[["expiry_label", "sku", "name", "category", "quantity", "expiry_date", "days_to_expiry", "units_at_risk", "value_at_risk"]].rename(
            columns={"expiry_label": "Level", "sku": "SKU", "name": "Product", "category": "Category", "quantity": "Qty",
                     "expiry_date": "Expiry", "days_to_expiry": "Days left", "units_at_risk": "Units at risk", "value_at_risk": "Value at risk"})
        st.caption(f"{len(rep)} batch(es)")
        ui.table(rep, {"Value at risk": ui.money_col("Value at risk"), "Days left": st.column_config.NumberColumn("Days left", format="%d")})
        _dl(rep, "expiring_products_report")

    with tabs[2]:
        df = P[P["overstock"]].sort_values("days_cover", ascending=False)
        rep = df[["sku", "name", "category", "quantity", "forecast_14d", "days_cover", "cover_threshold", "stock_value", "confidence"]].rename(
            columns={"sku": "SKU", "name": "Product", "category": "Category", "quantity": "Stock", "forecast_14d": "Forecast 14d",
                     "days_cover": "Days of cover", "cover_threshold": "Threshold (days)", "stock_value": "Stock value", "confidence": "Forecast confidence"})
        rep["Days of cover"] = rep["Days of cover"].replace(float("inf"), 9999)
        st.caption(f"{len(rep)} overstocked product(s) – stock exceeds forecast demand for longer than the product can sensibly be held.")
        ui.table(rep, {"Stock value": ui.money_col("Stock value"), "Forecast 14d": st.column_config.NumberColumn("Forecast 14d", format="%.0f"),
                       "Days of cover": st.column_config.NumberColumn("Days of cover", format="%.0f"),
                       "Threshold (days)": st.column_config.NumberColumn("Threshold (days)", format="%.0f")})
        _dl(rep, "overstock_report")

    with tabs[3]:
        df = P[P["slow"]].sort_values("velocity_30d")
        rep = df[["sku", "name", "category", "quantity", "velocity_30d", "stock_value", "days_cover"]].rename(
            columns={"sku": "SKU", "name": "Product", "category": "Category", "quantity": "Stock", "velocity_30d": "Units/day (30d)",
                     "stock_value": "Stock value", "days_cover": "Days of cover"})
        rep["Days of cover"] = rep["Days of cover"].replace(float("inf"), 9999)
        st.caption(f"{len(rep)} slow-moving product(s) – selling below {ctx.settings['slow_velocity']:g} units/day (adjustable in Settings).")
        ui.table(rep, {"Stock value": ui.money_col("Stock value"), "Units/day (30d)": st.column_config.NumberColumn("Units/day (30d)", format="%.2f"),
                       "Days of cover": st.column_config.NumberColumn("Days of cover", format="%.0f")})
        _dl(rep, "slow_moving_report")

    with tabs[4]:
        recs = pd.DataFrame(A.recs)
        if recs.empty:
            ui.info("No discount recommendations right now.")
        else:
            disc = recs[recs["discount_pct"].notna()]
            rep = disc[["priority", "sku", "product_name", "category", "discount_pct", "units_at_risk", "value_at_risk", "rationale"]].rename(
                columns={"priority": "Priority", "sku": "SKU", "product_name": "Product", "category": "Category",
                         "discount_pct": "Discount %", "units_at_risk": "Units at risk", "value_at_risk": "Value at risk",
                         "rationale": "Why"})
            st.caption(f"{len(rep)} discount suggestion(s). Approve or reject them in the Action Centre.")
            ui.table(rep, {"Value at risk": ui.money_col("Value at risk"), "Discount %": st.column_config.NumberColumn("Discount %", format="%d")})
            _dl(rep, "discount_recommendations_report")
