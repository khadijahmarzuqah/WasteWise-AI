import pandas as pd
import streamlit as st

from core import charts, config, ui


def _view(df):
    d = df.copy()
    d["risk"] = d.apply(
        lambda r: "🔴 High" if (r["expiry_level"] == "Expired" or (pd.notna(r["risk_pct"]) and r["risk_pct"] >= 0.5)
                                or (r["days_to_expiry"] <= 3 and pd.notna(r["units_at_risk"]) and r["units_at_risk"] > 0))
        else ("🟠 Medium" if pd.notna(r["units_at_risk"]) and r["units_at_risk"] > 0 else
              ("❔ Unknown (no forecast)" if pd.isna(r["units_at_risk"]) else "🟢 Low")), axis=1)
    out = d[["expiry_label", "name", "category", "quantity", "expiry_date", "days_to_expiry", "units_at_risk", "value_at_risk", "risk"]]
    return out.rename(columns={"expiry_label": "Warning level", "name": "Product", "category": "Category",
                               "quantity": "Batch qty", "expiry_date": "Expiry date", "days_to_expiry": "Days left",
                               "units_at_risk": "Units at risk", "value_at_risk": "Value at risk", "risk": "Waste risk"})


def render(ctx):
    A = ctx.analysis
    ui.page_title("Expiry Monitoring", "Batches expiring within 3, 7 and 15 days, with forecast waste risk.")
    ui.sample_banner(A.products)
    B = A.batches
    if B.empty:
        ui.empty_state("No stock batches", "Add inventory with expiry dates to start monitoring.")
        return

    d = B["days_to_expiry"]
    expired = B[B["expiry_level"] == "Expired"]
    w3, w7, w15 = (B[(d >= 0) & (d <= n)] for n in config.EXPIRY_WINDOWS)
    ui.stat_cards([
        dict(label="Expired", value=len(expired), sub="batches to remove now", tone="danger" if len(expired) else ""),
        dict(label="Within 3 days", value=len(w3), sub=f'{int(w3["quantity"].sum()):,} units · critical', tone="danger" if len(w3) else ""),
        dict(label="Within 7 days", value=len(w7), sub=f'{int(w7["quantity"].sum()):,} units · warning', tone="warn"),
        dict(label="Within 15 days", value=len(w15), sub=f'{int(w15["quantity"].sum()):,} units · watch', tone="warn"),
    ])
    st.markdown("**Warning levels:** ⛔ Expired · 🔴 Critical ≤3 days · 🟠 Warning ≤7 days · 🟡 Watch ≤15 days · 🟢 OK. "
                "Windows are cumulative (≤7 days includes ≤3 days).")

    tabs = st.tabs(["Within 3 days", "Within 7 days", "Within 15 days", "Expired", "All batches"])
    for tab, df, name in zip(tabs, [w3, w7, w15, expired, B], ["3 days", "7 days", "15 days", "expired", "all"]):
        with tab:
            if df.empty:
                st.success("Nothing here – all clear.")
                continue
            show = _view(df)
            ui.table(show, {"Value at risk": ui.money_col("Value at risk"),
                            "Days left": st.column_config.NumberColumn("Days left", format="%d"),
                            "Units at risk": st.column_config.NumberColumn("Units at risk", format="%d")}, height=min(520, 60 + 36 * len(show)))
            st.download_button("⬇️ Download (CSV)", ui.csv_bytes(show), f"expiry_{name.replace(' ', '_')}.csv", "text/csv", key=f"dl_exp_{name}")

    with st.container(border=True):
        st.plotly_chart(charts.expiry_buckets(B), use_container_width=True)
    st.button("See suggested actions →", type="primary", on_click=ui.goto, args=(config.NAV_ACTIONS,))
    st.caption("Waste risk = units forecast not to sell before expiry (FEFO). It is an estimate from recent sales, "
               "not a guarantee. 'Unknown' means the product has too little sales history to forecast.")
