import streamlit as st

from core import charts, config, db, forecast, ui


def render(ctx):
    A, t = ctx.analysis, ctx.analysis.totals
    ui.hero(config.APP_NAME, config.TAGLINE)
    ui.sample_banner(A.products)

    if t["total_products"] == 0:
        ui.empty_state("No inventory yet",
                       "Open Data Management to upload your inventory and sales CSV files, or load the sample data.")
        return

    pending = len(db.read_recommendations("Pending"))
    ui.stat_cards([
        dict(label="Total products", value=f'{t["total_products"]:,}', sub=f'{t["total_qty"]:,} units in stock · {ui.inr(t["stock_value"])}', tone="dark"),
        dict(label="Total inventory qty", value=f'{t["total_qty"]:,}', sub="units across all batches"),
        dict(label="Near-expiry products", value=t["near_expiry"], sub=f'{t["critical"]} critical (≤3 days) · within 15 days',
             tone="danger" if t["critical"] else "warn"),
        dict(label="Overstocked", value=t["overstocked"], sub="stock exceeds forecast demand", tone="warn"),
        dict(label="Slow-moving", value=t["slow"], sub=f'< {ctx.settings["slow_velocity"]:g} units/day (30-day avg)', tone="info"),
        dict(label="Est. waste risk", value=ui.inr(t["value_at_risk"]),
             sub=f'{t["units_at_risk"]:,} units · {t["risk_pct"]:.1%} of stock value', tone="danger" if t["value_at_risk"] > 0 else ""),
    ])

    c1, c2, c3 = st.columns([1, 1, 1])
    c1.button("Review expiring items →", type="primary", on_click=ui.goto, args=(config.NAV_EXPIRY,), use_container_width=True)
    c2.button(f"Open Action Centre ({pending} pending) →", on_click=ui.goto, args=(config.NAV_ACTIONS,), use_container_width=True)
    c3.button("View reports →", on_click=ui.goto, args=(config.NAV_REPORTS,), use_container_width=True)

    left, right = st.columns([3, 2])
    with left:
        with st.container(border=True):
            names = A.products.set_index("sku")["name"].to_dict()
            options = ["All products (back-tested)"] + [f"{r.sku} · {names[r.sku]}" for r in A.forecasts.values() if r.available]
            ui.reset_if_stale("dash_fc_sel", options)
            choice = st.selectbox("Forecast view", options, key="dash_fc_sel")
            skus = None if choice == options[0] else [choice.split(" · ")[0]]
            df, n = forecast.forecast_vs_actual(A.forecasts, skus)
            if df.empty:
                ui.info("Not enough sales history yet to draw a forecast (at least 28 days per product are needed "
                        "for the all-products back-test).")
            else:
                st.plotly_chart(charts.forecast_chart(df), use_container_width=True)
                st.caption(f"Based on {n} product(s). Dashed amber = what the model would have predicted for "
                           "recent days it had not seen; dotted green = forecast ahead. Forecast confidence is "
                           "shown on the Demand Forecast page.")
    with right:
        with st.container(border=True):
            st.plotly_chart(charts.category_donut(A.products), use_container_width=True)

    l2, r2 = st.columns(2)
    with l2:
        with st.container(border=True):
            if len(A.batches):
                st.plotly_chart(charts.expiry_buckets(A.batches), use_container_width=True)
    with r2:
        with st.container(border=True):
            if len(A.batches) and A.batches["value_at_risk"].fillna(0).sum() > 0:
                st.plotly_chart(charts.risk_by_category(A.batches), use_container_width=True)
            else:
                ui.info("No forecast waste risk right now.")

    st.markdown("### Highest waste-risk batches")
    b = A.batches[(A.batches["units_at_risk"].fillna(0) > 0)].sort_values("value_at_risk", ascending=False).head(8)
    if b.empty:
        ui.info("No batches are currently forecast to go unsold before expiry.")
    else:
        show = b[["name", "category", "quantity", "expiry_date", "days_to_expiry", "expiry_label", "units_at_risk", "value_at_risk"]]
        show = show.rename(columns={"name": "Product", "category": "Category", "quantity": "Batch qty",
                                    "expiry_date": "Expiry", "days_to_expiry": "Days left", "expiry_label": "Level",
                                    "units_at_risk": "Units at risk", "value_at_risk": "Value at risk"})
        ui.table(show, {"Value at risk": ui.money_col("Value at risk"), "Days left": st.column_config.NumberColumn("Days left", format="%d"),
                        "Units at risk": st.column_config.NumberColumn("Units at risk", format="%d")})
    if t["no_forecast"]:
        st.caption(f"ℹ️ {t['no_forecast']} product(s) have under {forecast.MIN_DAYS} days of sales history, so no forecast "
                   "or waste-risk estimate is shown for them.")
