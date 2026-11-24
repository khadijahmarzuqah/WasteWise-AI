import pandas as pd
import streamlit as st

from core import charts, forecast, ui


def render(ctx):
    A = ctx.analysis
    ui.page_title("Demand Forecasting",
                  "A transparent baseline: moving average vs. a weekday-aware Ridge regression, chosen by back-test.")
    ui.sample_banner(A.products)
    P = A.products
    if P.empty:
        ui.empty_state("No products", "Upload inventory and sales data first.")
        return

    ui.info("How much to trust this: products with fewer than 14 days of sales get no forecast; 14–27 days get a rough "
            "moving average (confidence Low); 28+ days are back-tested on the most recent days and rated High / Medium / Low "
            "from the hold-out error. A short history can never be rated High.")

    names = P.set_index("sku")["name"].to_dict()
    opts = ["All products"] + [f"{s} · {names[s]}" for s in P["sku"]]
    ui.reset_if_stale("fc_sel", opts)
    choice = st.selectbox("Product", opts, key="fc_sel")
    skus = None if choice == opts[0] else [choice.split(" · ")[0]]

    with st.container(border=True):
        df, n = forecast.forecast_vs_actual(A.forecasts, skus)
        if df.empty:
            msg = "No forecast available." if skus is None else A.forecasts[skus[0]].note
            st.warning(msg)
        else:
            st.plotly_chart(charts.forecast_chart(df), use_container_width=True)
            if skus is None:
                st.caption(f"Aggregate of {n} product(s) with at least 28 days of history.")

    if skus:
        r = A.forecasts[skus[0]]
        p = P.set_index("sku").loc[skus[0]]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Method", r.method)
        c2.metric("Confidence", r.confidence)
        c3.metric("History", f"{r.n_days} days")
        c4.metric("Back-test error (WAPE)", "n/a" if pd.isna(r.wape) else f"{r.wape:.0%}")
        st.write(r.note)
        if r.available:
            tbl = r.future.assign(date=r.future["date"].dt.strftime("%a %d %b"),
                                  forecast=r.future["forecast"].round(1)).rename(columns={"date": "Date", "forecast": "Expected units"})
            l, rgt = st.columns([1, 1])
            with l:
                ui.table(tbl)
            with rgt:
                st.metric("Expected demand, next 14 days", f"{p['forecast_14d']:,.0f} units")
                st.metric("Stock on hand", f"{int(p['quantity']):,} units")
                cover = "∞" if p["days_cover"] == float("inf") else f"{p['days_cover']:,.0f} days"
                st.metric("Days of cover", cover)
                st.write(f"Overstock threshold: **{p['cover_threshold']:,.0f} days** · status: **{p['status']}**")
        return

    st.markdown("### Forecast demand vs available inventory")
    t = P[["sku", "name", "category", "quantity", "forecast_14d", "days_cover", "cover_threshold", "method",
           "confidence", "overstock"]].copy()
    t["Overstock?"] = t.apply(lambda r: "⚠️ Possible overstock" if r["overstock"] else
                              ("— no forecast" if pd.isna(r["forecast_14d"]) else "OK"), axis=1)
    t["days_cover"] = t["days_cover"].replace(float("inf"), 9999)
    t = t.drop(columns="overstock").rename(columns={
        "sku": "SKU", "name": "Product", "category": "Category", "quantity": "Stock", "forecast_14d": "Forecast 14d",
        "days_cover": "Days of cover", "cover_threshold": "Threshold (days)", "method": "Method", "confidence": "Confidence"})
    only = st.toggle("Show only possible overstock", value=False, key="fc_only_over")
    if only:
        t = t[t["Overstock?"].str.startswith("⚠️")]
    ui.table(t, {"Forecast 14d": st.column_config.NumberColumn("Forecast 14d", format="%.0f"),
                 "Days of cover": st.column_config.NumberColumn("Days of cover", format="%.0f"),
                 "Threshold (days)": st.column_config.NumberColumn("Threshold (days)", format="%.0f")}, height=420)
    st.download_button("⬇️ Download forecast table (CSV)", ui.csv_bytes(t), "forecast_vs_inventory.csv", "text/csv")
    with st.container(border=True):
        st.plotly_chart(charts.stock_vs_demand(P), use_container_width=True)
