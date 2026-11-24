import pandas as pd
import streamlit as st

from core import db, recommend, ui

TYPE_ICON = {"Remove expired stock": "⛔", "Prioritise near-expiry stock": "⏱️", "Monitor slow-moving product": "👁️",
             "Reduce next reorder quantity": "📉", "Skip next reorder": "⏸️"}


def _icon(action: str) -> str:
    return "🏷️" if "discount" in action else TYPE_ICON.get(action, "•")


def render(ctx):
    ui.page_title("Action Centre", "Review suggested actions. Approve or reject – decisions are stored, nothing changes automatically.")
    ui.sample_banner(ctx.analysis.products)
    ui.info("WasteWise AI never changes real prices or purchase orders. Approving a suggestion records your decision "
            "so your team can carry it out in your own pricing / ordering system.")

    pending = db.read_recommendations("Pending")
    all_recs = db.read_recommendations()
    n_app = int((all_recs["status"] == "Approved").sum()) if len(all_recs) else 0
    n_rej = int((all_recs["status"] == "Rejected").sum()) if len(all_recs) else 0
    ui.stat_cards([
        dict(label="Pending", value=len(pending), sub="awaiting review", tone="warn" if len(pending) else ""),
        dict(label="High priority", value=int((pending["priority"] == "High").sum()) if len(pending) else 0, sub="pending", tone="danger"),
        dict(label="Approved", value=n_app, sub="all time"),
        dict(label="Rejected", value=n_rej, sub="all time", tone="info"),
    ])

    t_pending, t_hist, t_rules = st.tabs(["Suggested actions", "Action history", "How suggestions work"])

    with t_pending:
        if pending.empty:
            st.success("🎉 No pending suggestions. Everything has been reviewed.")
        else:
            c1, c2, c3 = st.columns(3)
            prio = c1.multiselect("Priority", ["High", "Medium", "Low"], default=["High", "Medium", "Low"], key="act_prio")
            kinds = sorted(pending["action_type"].unique())
            kind = c2.multiselect("Action type", kinds, key="act_kind")
            limit = c3.selectbox("Show", [10, 25, 50, "All"], index=0, key="act_limit")
            v = pending[pending["priority"].isin(prio)]
            if kind:
                v = v[v["action_type"].isin(kind)]
            total = len(v)
            if limit != "All":
                v = v.head(int(limit))
            st.caption(f"Showing {len(v)} of {total} suggestion(s), highest priority first.")
            for r in v.itertuples():
                with st.container(border=True):
                    left, right = st.columns([5, 2])
                    with left:
                        extra = ""
                        if pd.notna(r.value_at_risk) and r.value_at_risk > 0:
                            extra = f" · value at risk {ui.inr(r.value_at_risk)}"
                        st.markdown(
                            f'<div class="ww-rec-title">{_icon(r.action_type)} {ui.esc(r.action_type)} — {ui.esc(r.product_name)}</div>'
                            f'<div class="ww-rec-meta">{ui.esc(r.sku)} · {ui.esc(r.category)}{extra} &nbsp; {ui.badge(r.priority)}</div>'
                            f'<div class="ww-rec-text">{ui.esc(r.rationale)}</div>', unsafe_allow_html=True)
                    with right:
                        note = st.text_input("Note (optional)", key=f"note_{r.rec_id}", placeholder="e.g. approved by manager")
                        b1, b2 = st.columns(2)
                        if b1.button("Approve", key=f"ok_{r.rec_id}", type="primary", use_container_width=True):
                            db.decide(r.rec_id, "Approved", note)
                            st.rerun()
                        if b2.button("Reject", key=f"no_{r.rec_id}", use_container_width=True):
                            db.decide(r.rec_id, "Rejected", note)
                            st.rerun()

    with t_hist:
        log = db.read_action_log()
        if log.empty:
            ui.info("No decisions yet. Approve or reject a suggestion and it will appear here.")
        else:
            show = log.rename(columns={"decided_at": "Decided at", "sku": "SKU", "product_name": "Product",
                                       "action_type": "Action", "decision": "Decision", "note": "Note", "rationale": "Why it was suggested"})
            show["Decision"] = show["Decision"].map({"Approved": "✅ Approved", "Rejected": "❌ Rejected"})
            ui.table(show, height=480)
            st.download_button("⬇️ Download action history (CSV)", ui.csv_bytes(log), "action_history.csv", "text/csv")
        with st.expander("Danger zone"):
            if st.checkbox("I want to clear all approval / rejection history", key="clear_hist_ok"):
                if st.button("Clear history", key="clear_hist"):
                    db.clear_action_history()
                    st.rerun()

    with t_rules:
        st.markdown(recommend.RULES_MARKDOWN)
