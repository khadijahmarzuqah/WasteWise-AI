import streamlit as st

from core import db, sample_data, ui, validation


def _show_result(res, kind):
    """Display validation outcome. Returns True if the clean rows may be imported."""
    if res.fatal:
        st.error(f"❌ {res.fatal}")
        return False
    st.markdown(f"**{res.n_rows:,}** row(s) read · **{res.n_valid:,}** valid · **{len(res.row_errors):,}** with problems")
    for w in res.warnings:
        st.warning(w)
    allow = True
    if res.row_errors:
        st.error(f"{len(res.row_errors)} row(s) have problems and will be skipped. Fix them in your file and re-upload, "
                 "or import the valid rows only.")
        import pandas as pd
        err = pd.DataFrame(res.row_errors[:50], columns=["Row in file (header = row 1)", "Problem"])
        ui.table(err)
        if len(res.row_errors) > 50:
            st.caption(f"…and {len(res.row_errors) - 50} more.")
        if res.n_valid == 0:
            return False
        allow = st.checkbox(f"Import the {res.n_valid:,} valid row(s) and skip the rest", key=f"ok_partial_{kind}")
    else:
        st.success("✅ All rows passed validation.")
    if res.n_valid:
        with st.expander("Preview of rows that will be imported"):
            ui.table(res.clean.head(20))
    return allow


def _flash():
    m = st.session_state.pop("dm_flash", None)
    if m:
        st.success(m)


def render(ctx):
    A = ctx.analysis
    ui.page_title("Data Management", "Upload CSV files, download templates, export reports and reset the demo data.")
    ui.sample_banner(A.products)
    _flash()
    t_inv, t_sales, t_tpl, t_exp, t_reset = st.tabs(
        ["Upload inventory", "Upload sales", "Templates & sample CSVs", "Export", "Reset"])

    # ------------------------------------------------------ inventory
    with t_inv:
        st.markdown("Upload a CSV with **one row per stock batch**. Required columns: "
                    "`sku, name, category, price, quantity, expiry_date` (YYYY-MM-DD, may be blank). "
                    "Optional: `cost, shelf_life_days, reorder_qty`.")
        up = st.file_uploader("Inventory CSV", type=["csv"], key="up_inv")
        mode = st.radio("How should it be imported?",
                        ["Update the products in this file (replace their batches, keep other products)",
                         "Replace ALL inventory (removes products not in the file and their sales)"], key="inv_mode")
        if up is not None:
            raw, err = validation.read_csv(up)
            if err:
                st.error(f"❌ {err}")
            else:
                res = validation.validate_inventory(raw)
                if _show_result(res, "inv"):
                    if st.button(f"Import {res.n_valid:,} row(s)", type="primary", key="do_inv"):
                        out = db.import_inventory(res.clean, "replace" if mode.startswith("Replace") else "merge")
                        st.session_state["dm_flash"] = (f"Imported {out['products']} product(s) and {out['batches']} batch(es). "
                                                        "Upload sales history next so forecasts can be calculated.")
                        st.rerun()

    # ---------------------------------------------------------- sales
    with t_sales:
        st.markdown("Upload daily sales. Required columns: `date` (YYYY-MM-DD), `sku`, `units_sold`. "
                    "Every `sku` must already exist in inventory. Days without a row are treated as **zero sales**, "
                    "so include a row for every day you were open. Re-uploading the same date and SKU overwrites it.")
        up = st.file_uploader("Sales CSV", type=["csv"], key="up_sales")
        smode = st.radio("How should it be imported?",
                         ["Add / overwrite matching dates", "Replace ALL existing sales history"], key="sales_mode")
        if up is not None:
            raw, err = validation.read_csv(up)
            if err:
                st.error(f"❌ {err}")
            else:
                res = validation.validate_sales(raw, A.products["sku"] if len(A.products) else [])
                if _show_result(res, "sales"):
                    if st.button(f"Import {res.n_valid:,} row(s)", type="primary", key="do_sales"):
                        out = db.import_sales(res.clean, "replace" if smode.startswith("Replace") else "merge")
                        st.session_state["dm_flash"] = f"Imported {out['rows']:,} sales row(s)."
                        st.rerun()

    # ------------------------------------------------------ templates
    with t_tpl:
        st.markdown("**Templates** (a few example rows – edit them with your own data)")
        c1, c2 = st.columns(2)
        c1.download_button("⬇️ Inventory template", ui.csv_bytes(sample_data.template_inventory_csv()),
                           "inventory_template.csv", "text/csv", use_container_width=True)
        c2.download_button("⬇️ Sales template", ui.csv_bytes(sample_data.template_sales_csv()),
                           "sales_template.csv", "text/csv", use_container_width=True)
        st.markdown("**SYNTHETIC sample datasets** (full demo data, dated relative to today)")
        c3, c4 = st.columns(2)
        c3.download_button("⬇️ Sample inventory (SYNTHETIC)", ui.csv_bytes(sample_data.sample_inventory_csv()),
                           "sample_inventory.csv", "text/csv", use_container_width=True)
        c4.download_button("⬇️ Sample sales – 90 days (SYNTHETIC)", ui.csv_bytes(sample_data.sample_sales_csv()),
                           "sample_sales.csv", "text/csv", use_container_width=True)
        st.caption("Tip: download the sample files, change a few values, and upload them to see validation and imports in action.")

    # --------------------------------------------------------- export
    with t_exp:
        if A.products.empty:
            ui.info("Nothing to export yet.")
        else:
            inv = A.batches[["sku", "name", "category", "price", "quantity", "expiry_date", "days_to_expiry", "expiry_level"]]
            inv_products = A.products[["sku", "name", "category", "price", "cost", "quantity", "nearest_expiry", "days_left", "status"]]
            waste = A.batches[["sku", "name", "category", "quantity", "expiry_date", "days_to_expiry", "expiry_level",
                               "expected_sold", "units_at_risk", "value_at_risk"]]
            c1, c2, c3 = st.columns(3)
            c1.download_button("⬇️ Inventory (batch level)", ui.csv_bytes(inv), "inventory_batches.csv", "text/csv", use_container_width=True)
            c2.download_button("⬇️ Inventory (product level)", ui.csv_bytes(inv_products), "inventory_products.csv", "text/csv", use_container_width=True)
            c3.download_button("⬇️ Waste-risk report", ui.csv_bytes(waste), "waste_risk_report.csv", "text/csv", use_container_width=True)
            st.caption("More reports (expiring, overstock, slow-moving, discounts) are on the Reports page.")

    # ---------------------------------------------------------- reset
    with t_reset:
        st.markdown("**Reload the SYNTHETIC sample data** – replaces all products, stock, sales and action history.")
        if st.checkbox("I understand this replaces my current data", key="reset_ok"):
            if st.button("Reload sample data", key="do_reset"):
                db.seed_sample()
                st.session_state["dm_flash"] = "Sample data reloaded (all dates are relative to today)."
                st.rerun()
        st.markdown("**Clear everything** – start with an empty store, then upload your own CSVs.")
        if st.checkbox("I understand this deletes all data", key="clear_ok"):
            if st.button("Delete all data", key="do_clear"):
                db.clear_all_data()
                st.session_state["dm_flash"] = "All data deleted."
                st.rerun()
