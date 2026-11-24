import streamlit as st

from core import config, db, ui


def render(ctx):
    ui.page_title("Settings & About", "Tune the detection thresholds and read how WasteWise AI works.")
    s = ctx.settings
    with st.container(border=True):
        st.markdown("**Detection thresholds**")
        with st.form("settings_form"):
            c1, c2, c3 = st.columns(3)
            slow = c1.number_input("Slow-moving: below (units/day)", min_value=0.0, value=float(s["slow_velocity"]), step=0.1,
                                   help="Average units sold per day over the last 30 days.")
            cap = c2.number_input("Overstock cap (days of cover)", min_value=3.0, value=float(s["overstock_cover_cap"]), step=1.0,
                                  help="A product is overstocked when stock covers more than 1.25 × min(this cap, shelf life) days of forecast demand.")
            tgt = c3.number_input("Target cover after reorder (days)", min_value=1.0, value=float(s["target_cover_days"]), step=1.0,
                                  help="Used to size the 'reduce next reorder' suggestion.")
            if st.form_submit_button("Save settings", type="primary"):
                db.save_settings({"slow_velocity": slow, "overstock_cover_cap": cap, "target_cover_days": tgt})
                st.success("Saved. All pages now use the new thresholds.")
                st.rerun()

    st.markdown("### About WasteWise AI")
    st.markdown(f"""
**{config.APP_NAME}** – *{config.TAGLINE}*

An AI-assisted retail waste prediction and prevention tool built by **Team Pixel Panthers** (Maatram HackForge 2026–27, MH26-06).

**Pipeline:** CSV upload → pandas validation → forecast + risk checks → rule-based recommendations → Streamlit dashboard → staff approval, with everything stored in SQLite.

**What the "AI" really is:** a per-product demand forecast (moving average vs. scikit-learn Ridge regression with weekday seasonality, chosen by back-test) feeding transparent, rule-based recommendations. There is no black box and no external AI service.

**Honest limitations**
- Forecasts need history: under 14 days of sales → no forecast; under 28 days → rough moving average only.
- It does not know about promotions, festivals, weather, stock-outs or price changes (listed as future enhancements).
- Waste risk is an *estimate*, based on recent sales and first-expiry-first-out selling.
- Demo data is **synthetic**; no real-store results are shown.
- Suggestions never change prices or orders. Approval only records a decision.
""")
