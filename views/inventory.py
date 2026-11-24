from datetime import date

import pandas as pd
import streamlit as st

from core import config, db, ui

STATUS_FILTERS = ["All", "Expired", "Critical (≤3 days)", "Warning (≤7 days)", "Watch (≤15 days)",
                  "Overstocked", "Slow-moving", "Healthy", "Out of stock"]


def _flash():
    msg = st.session_state.pop("inv_flash", None)
    if msg:
        st.success(msg)


def _category_input(label, key, default=None):
    # Inside st.form widgets do not rerun until submit, so the custom box is always shown.
    options = config.CATEGORIES + ["Other (use the box below)"]
    idx = options.index(default) if default in options else (len(options) - 1 if default else 0)
    sel = st.selectbox(label, options, index=idx, key=key + "_sel")
    custom = st.text_input("Custom category (only if 'Other' is selected)",
                           value=default if default and default not in config.CATEGORIES else "",
                           key=key + "_custom").strip()
    return custom if sel.startswith("Other") else sel


def _opt_int(v):
    return None if v in (None, 0, 0.0) else int(v)


def render(ctx):
    A = ctx.analysis
    ui.page_title("Inventory Management", "View, add, edit and delete products, stock batches and expiry dates.")
    ui.sample_banner(A.products)
    _flash()
    tab_all, tab_add, tab_edit = st.tabs(["All products", "➕ Add product", "✏️ Edit / delete"])

    # ------------------------------------------------------------ list
    with tab_all:
        P = A.products
        if P.empty:
            ui.empty_state("No products", "Add a product in the next tab or upload a CSV in Data Management.")
        else:
            c1, c2, c3 = st.columns([2, 2, 2])
            q = c1.text_input("Search name or SKU", key="inv_q", placeholder="e.g. milk or MLK001")
            cats = c2.multiselect("Category", sorted(P["category"].unique()), key="inv_cat")
            stat = c3.selectbox("Status", STATUS_FILTERS, key="inv_status")
            v = P.copy()
            if q:
                m = v["name"].str.contains(q, case=False, regex=False) | v["sku"].str.contains(q, case=False, regex=False)
                v = v[m]
            if cats:
                v = v[v["category"].isin(cats)]
            if stat != "All":
                key = stat.split(" (")[0]
                v = v[v["status"].str.contains(key, regex=False)]
            st.caption(f"Showing {len(v)} of {len(P)} products")
            out = v[["sku", "name", "category", "price", "quantity", "nearest_expiry", "days_left", "n_batches", "status"]].rename(
                columns={"sku": "SKU", "name": "Product", "category": "Category", "price": "Price", "quantity": "Stock qty",
                         "nearest_expiry": "Nearest expiry", "days_left": "Days left", "n_batches": "Batches", "status": "Status"})
            ui.table(out, {"Price": ui.money_col("Price", 2), "Days left": st.column_config.NumberColumn("Days left", format="%d"),
                           "Stock qty": st.column_config.NumberColumn("Stock qty", format="%d")}, height=480)
            st.download_button("⬇️ Download these products (CSV)", ui.csv_bytes(out), "inventory_products.csv", "text/csv")

    # ------------------------------------------------------------- add
    with tab_add:
        with st.form("add_product", clear_on_submit=True):
            c1, c2 = st.columns(2)
            sku = c1.text_input("SKU *", placeholder="e.g. MLK010")
            name = c2.text_input("Product name *")
            c3, c4, c5 = st.columns(3)
            with c3:
                category = _category_input("Category *", "add_cat")
            price = c4.number_input("Selling price *", min_value=0.0, value=0.0, step=1.0, format="%.2f")
            cost = c5.number_input("Unit cost (optional)", min_value=0.0, value=0.0, step=1.0, format="%.2f")
            c6, c7, c8 = st.columns(3)
            shelf = c6.number_input("Shelf life (days, optional)", min_value=0, value=0, step=1)
            reorder = c7.number_input("Usual reorder qty", min_value=0, value=0, step=1)
            qty = c8.number_input("Initial stock quantity", min_value=0, value=0, step=1)
            has_exp = st.checkbox("This product has an expiry date", value=True)
            exp = st.date_input("Expiry date of initial stock", value=date.today())
            ok = st.form_submit_button("Add product", type="primary")
        if ok:
            if not sku.strip() or not name.strip() or not category:
                st.error("SKU, product name and category are required.")
            elif price <= 0:
                st.error("Selling price must be greater than 0.")
            elif db.sku_exists(sku.strip()):
                st.error(f"SKU '{sku.strip()}' already exists. Use a different SKU or edit the existing product.")
            else:
                db.add_product(sku.strip(), name, category, price, cost or None, _opt_int(shelf), reorder,
                               quantity=qty or None, expiry_date=exp.isoformat() if has_exp else None)
                st.session_state["inv_flash"] = f"Added {name.strip()} ({sku.strip()})."
                st.rerun()
        st.caption("Tip: add sales history for new products via Data Management → Upload sales CSV, "
                   "otherwise they have no forecast.")

    # ------------------------------------------------------ edit/delete
    with tab_edit:
        P = A.products
        if P.empty:
            ui.info("Nothing to edit yet.")
            return
        labels = {r.sku: f"{r.sku} · {r.name}" for r in P.itertuples()}
        ui.reset_if_stale("edit_sku", labels)
        sku = st.selectbox("Select product", list(labels), format_func=lambda s: labels[s], key="edit_sku")
        p = P.set_index("sku").loc[sku]

        with st.container(border=True):
            st.markdown("**Product details**")
            with st.form(f"edit_prod_{sku}"):
                c1, c2 = st.columns(2)
                name = c1.text_input("Product name", value=p["name"])
                with c2:
                    category = _category_input("Category", f"edit_cat_{sku}", p["category"])
                c3, c4 = st.columns(2)
                price = c3.number_input("Selling price", min_value=0.0, value=float(p["price"]), step=1.0, format="%.2f")
                cost = c4.number_input("Unit cost (0 = unknown)", min_value=0.0,
                                       value=0.0 if pd.isna(p["cost"]) else float(p["cost"]), step=1.0, format="%.2f")
                c5, c6 = st.columns(2)
                shelf = c5.number_input("Shelf life days (0 = unknown)", min_value=0,
                                        value=0 if pd.isna(p["shelf_life_days"]) else int(p["shelf_life_days"]), step=1)
                reorder = c6.number_input("Usual reorder qty", min_value=0, value=int(p["reorder_qty"]), step=1)
                saved = st.form_submit_button("Save changes", type="primary")
            if saved:
                if not name.strip() or not category or price <= 0:
                    st.error("Name, category and a price above 0 are required.")
                else:
                    db.update_product(sku, name, category, price, cost or None, _opt_int(shelf), reorder)
                    st.session_state["inv_flash"] = f"Saved changes to {sku}."
                    st.rerun()

        with st.container(border=True):
            st.markdown("**Stock batches & expiry dates**")
            bt = db.read_batches()
            bt = bt[bt["sku"] == sku]
            if bt.empty:
                st.caption("No stock batches for this product.")
            else:
                ui.table(bt[["batch_id", "quantity", "expiry_date", "received_date"]].rename(
                    columns={"batch_id": "Batch #", "quantity": "Quantity", "expiry_date": "Expiry", "received_date": "Received"}))
                ui.reset_if_stale(f"bsel_{sku}", list(bt["batch_id"]))
                bid = st.selectbox("Batch to edit", list(bt["batch_id"]), format_func=lambda i: f"Batch #{i}", key=f"bsel_{sku}")
                row = bt.set_index("batch_id").loc[bid]
                with st.form(f"edit_batch_{sku}_{bid}"):
                    c1, c2 = st.columns(2)
                    bq = c1.number_input("Quantity", min_value=0, value=int(row["quantity"]), step=1)
                    has = c2.checkbox("Has expiry date", value=bool(row["expiry_date"]))
                    try:
                        dv = date.fromisoformat(row["expiry_date"]) if row["expiry_date"] else date.today()
                    except ValueError:
                        dv = date.today()
                    bd = c2.date_input("Expiry date", value=dv)
                    c3, c4 = st.columns(2)
                    save_b = c3.form_submit_button("Update batch", type="primary")
                    del_b = c4.form_submit_button("Delete batch")
                if save_b:
                    db.update_batch(bid, bq, bd.isoformat() if has else None)
                    st.session_state["inv_flash"] = f"Updated batch #{bid}."
                    st.rerun()
                if del_b:
                    db.delete_batch(bid)
                    st.session_state["inv_flash"] = f"Deleted batch #{bid}."
                    st.rerun()
            with st.form(f"new_batch_{sku}", clear_on_submit=True):
                st.markdown("Add a new batch")
                c1, c2, c3 = st.columns(3)
                nq = c1.number_input("Quantity", min_value=1, value=10, step=1)
                nh = c2.checkbox("Has expiry date", value=True)
                nd = c3.date_input("Expiry date", value=date.today())
                add_b = st.form_submit_button("Add batch")
            if add_b:
                db.add_batch(sku, nq, nd.isoformat() if nh else None)
                st.session_state["inv_flash"] = f"Added a batch of {nq} to {sku}."
                st.rerun()

        with st.container(border=True):
            st.markdown("**Delete product**")
            st.caption("Removes the product, all its batches and its sales history. Past approval records are kept.")
            sure = st.checkbox(f"Yes, permanently delete {sku}", key=f"del_ok_{sku}")
            if st.button("🗑️ Delete product", disabled=not sure, key=f"del_btn_{sku}"):
                db.delete_product(sku)
                st.session_state["inv_flash"] = f"Deleted {sku}."
                st.rerun()
