"""WasteWise AI – Predict Waste. Prevent Loss. Protect Resources.

Run locally:  streamlit run app.py
"""
from datetime import date
from types import SimpleNamespace

import streamlit as st

st.set_page_config(page_title="WasteWise AI", page_icon="🌿", layout="wide", initial_sidebar_state="auto")

from core import analysis, config, db, ui  # noqa: E402
from views import (actions, dashboard, data_management, expiry, forecasting,  # noqa: E402
                   inventory, reports, settings_page)

ROUTES = {
    config.NAV_DASHBOARD: dashboard,
    config.NAV_INVENTORY: inventory,
    config.NAV_EXPIRY: expiry,
    config.NAV_FORECAST: forecasting,
    config.NAV_ACTIONS: actions,
    config.NAV_DATA: data_management,
    config.NAV_REPORTS: reports,
    config.NAV_SETTINGS: settings_page,
}


@st.cache_data(show_spinner="Analysing inventory and forecasting demand…")
def _analyse(version: int, settings: dict, today_iso: str):
    """Cached on (data version, settings, date); `version` changes on every DB write."""
    return analysis.build_analysis(db.read_products(), db.read_batches(), db.read_sales(),
                                   settings, date.fromisoformat(today_iso))


def main():
    db.init_db()            # cheap & idempotent; seeds sample data on the very first run
    ui.inject_css()

    settings = db.get_settings()
    today = date.today()
    A = _analyse(db.get_version(), settings, today.isoformat())

    # keep stored recommendations in sync with the latest analysis (once per data/settings state)
    sync_key = (db.get_version(), tuple(sorted(settings.items())), today.isoformat())
    if st.session_state.get("_synced") != sync_key:
        db.sync_recommendations(A.recs)
        st.session_state["_synced"] = sync_key

    ui.brand()
    st.session_state.setdefault("nav", config.NAV_DASHBOARD)
    page = st.sidebar.radio("Navigation", config.NAV_PAGES, key="nav", label_visibility="collapsed")

    pending = len(db.read_recommendations("Pending"))
    st.sidebar.markdown(
        f'<div class="ww-side-note"><b>{pending}</b> suggestion(s) awaiting review<br>'
        f'Data as of {today:%d %b %Y}</div>', unsafe_allow_html=True)
    if len(A.products) and int(A.products["is_sample"].sum()) > 0:
        st.sidebar.markdown('<div class="ww-side-note">🧪 <b>SAMPLE / SYNTHETIC DATA</b> in use</div>',
                            unsafe_allow_html=True)

    ctx = SimpleNamespace(analysis=A, settings=settings, today=today)
    ROUTES[page].render(ctx)


main()
