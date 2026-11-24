"""Tests for the WasteWise AI core logic. Run:  python -m pytest -q"""
import io
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import analysis, config, db, forecast, sample_data, validation  # noqa: E402

TODAY = date.today()


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    return config.DB_PATH


def run_analysis(settings=None):
    return analysis.build_analysis(db.read_products(), db.read_batches(), db.read_sales(),
                                   settings or db.get_settings(), TODAY)


# ----------------------------------------------------------------- database
def test_init_seeds_sample_and_persists(fresh_db):
    p = db.read_products()
    assert len(p) >= 30 and p["is_sample"].all()
    assert set(config.CATEGORIES) <= set(p["category"])
    v = db.get_version()
    db.init_db()                       # "restart": must not reseed or lose data
    assert len(db.read_products()) == len(p)
    assert db.get_version() == v


def test_crud_roundtrip(fresh_db):
    db.add_product("T001", "Test Item", "Snacks", 10, 7, 30, 20, quantity=50, expiry_date=(TODAY + timedelta(days=5)).isoformat())
    with pytest.raises(ValueError):
        db.add_product("T001", "Dup", "Snacks", 10)
    assert db.sku_exists("T001")
    db.update_product("T001", "Test Item 2", "Snacks", 12, 8, 30, 25)
    row = db.read_products().set_index("sku").loc["T001"]
    assert row["name"] == "Test Item 2" and row["price"] == 12 and row["is_sample"] == 0
    b = db.read_batches()
    bid = int(b[b["sku"] == "T001"]["batch_id"].iloc[0])
    db.update_batch(bid, 77, None)
    assert int(db.read_batches().set_index("batch_id").loc[bid, "quantity"]) == 77
    db.add_batch("T001", 5, TODAY.isoformat())
    db.delete_batch(bid)
    assert len(db.read_batches().query("sku=='T001'")) == 1
    v = db.get_version()
    db.delete_product("T001")
    assert not db.sku_exists("T001") and db.get_version() > v
    assert db.read_batches().query("sku=='T001'").empty


# --------------------------------------------------------------- validation
def _csv(text):
    df, err = validation.read_csv(text.encode())
    assert err is None
    return df


def test_inventory_validation_messages():
    text = ("sku,name,category,price,quantity,expiry_date\n"
            "A1,Milk,Milk,50,10,2026-12-01\n"
            "A2,Bad,Milk,-5,10,2026-12-01\n"
            "A3,Bad2,Milk,5,2.5,01/12/2026\n"
            ",NoSku,Milk,5,1,\n")
    r = validation.validate_inventory(_csv(text))
    assert r.fatal is None and r.n_rows == 4 and r.n_valid == 1
    msgs = dict(r.row_errors)
    assert "price" in msgs[3]
    assert "quantity" in msgs[4] and "expiry_date" in msgs[4]
    assert "sku is blank" in msgs[5]
    assert not r.ok


def test_inventory_missing_column_and_empty():
    r = validation.validate_inventory(_csv("sku,name\nA,B\n"))
    assert r.fatal and "category" in r.fatal and "quantity" in r.fatal
    df, err = validation.read_csv(b"")
    assert df is None and "empty" in err.lower()
    df, err = validation.read_csv(b"sku,name,category,price,quantity,expiry_date\n")
    assert validation.validate_inventory(df).fatal


def test_inventory_aliases_and_blank_expiry():
    r = validation.validate_inventory(_csv("SKU,Product Name,Category,Unit Price,Stock,Expiry\nA1,Rice,other grocery,100,5,\n"))
    assert r.ok and r.clean.iloc[0]["category"] == "Other Grocery"
    assert any("no expiry" in w for w in r.warnings)


def test_sales_validation():
    text = "date,sku,units_sold\n2026-01-01,A1,5\n2026-01-01,A1,3\n2026-01-02,ZZ,4\n2026-13-40,A1,2\n2026-01-03,A1,x\n"
    r = validation.validate_sales(_csv(text), ["A1"])
    assert r.n_valid == 1 and r.clean.iloc[0]["units"] == 8      # duplicates summed
    errs = dict(r.row_errors)
    assert "unknown SKU" in errs[4] and "date" in errs[5] and "units_sold" in errs[6]
    assert validation.validate_sales(_csv(text), []).fatal


def test_import_inventory_and_sales(fresh_db):
    inv = validation.validate_inventory(_csv(
        "sku,name,category,price,quantity,expiry_date,cost\n"
        f"N1,Milk A,Milk,60,100,{(TODAY + timedelta(days=4)).isoformat()},50\n"
        f"N1,Milk A,Milk,60,40,{(TODAY + timedelta(days=9)).isoformat()},50\n"
        "N2,Rice,Other Grocery,500,10,,\n")).clean
    out = db.import_inventory(inv, "replace")
    assert out == dict(products=2, batches=3)
    assert len(db.read_products()) == 2 and not db.read_products()["is_sample"].any()
    assert db.read_sales().empty                       # orphan sample sales removed
    rows = ["date,sku,units_sold"] + [f"{(TODAY - timedelta(days=i)).isoformat()},N1,{30 + i % 5}" for i in range(1, 31)]
    s = validation.validate_sales(_csv("\n".join(rows) + "\n"), db.read_products()["sku"])
    assert s.ok
    assert db.import_sales(s.clean)["rows"] == 30
    db.import_sales(s.clean)                           # re-import must not duplicate
    assert len(db.read_sales()) == 30
    # merge: replaces batches of N1 only
    db.import_inventory(inv[inv["sku"] == "N1"].head(1), "merge")
    b = db.read_batches()
    assert len(b[b["sku"] == "N1"]) == 1 and len(b[b["sku"] == "N2"]) == 1


# ------------------------------------------------------------------ forecast
def _series_df(days, level=20, weekly=True, seed=1):
    rng = np.random.default_rng(seed)
    d = pd.date_range(end=pd.Timestamp(TODAY) - pd.Timedelta(days=1), periods=days)
    mult = np.array([0.8, 0.8, 0.9, 1.0, 1.2, 1.4, 1.1])[d.dayofweek] if weekly else 1
    return pd.DataFrame({"sale_date": d, "units": rng.poisson(level * mult)})


def test_forecast_confidence_tiers():
    assert not forecast.forecast_sku("x", _series_df(6), TODAY).available          # honest: no forecast
    r = forecast.forecast_sku("x", _series_df(20), TODAY)
    assert r.available and r.confidence == "Low" and len(r.backtest) == 0
    r = forecast.forecast_sku("x", _series_df(90), TODAY)
    assert r.available and len(r.backtest) == 14 and len(r.future) == 14
    assert r.confidence in ("High", "Medium") and r.wape < 0.45
    assert (r.future["forecast"] >= 0).all()
    assert 12 < r.daily_rate < 32                                                  # sane level
    assert forecast.demand_over(r, 30) > forecast.demand_over(r, 14) > forecast.demand_over(r, 3) > 0
    assert np.isnan(forecast.demand_over(forecast.forecast_sku("x", _series_df(3), TODAY), 5))


def test_ridge_used_when_seasonal():
    r = forecast.forecast_sku("x", _series_df(90, level=40), TODAY)
    assert "Ridge" in r.method


# ------------------------------------------------------------ analysis/recs
def test_full_analysis_on_sample_data(fresh_db):
    A = run_analysis()
    t = A.totals
    assert t["total_products"] == len(db.read_products())
    assert t["near_expiry"] > 0 and t["overstocked"] > 0 and t["slow"] > 0
    assert t["value_at_risk"] > 0 and t["no_forecast"] >= 1
    # numbers come from data: total qty equals the batches table sum
    assert t["total_qty"] == int(db.read_batches()["quantity"].sum())
    P = A.products.set_index("sku")
    assert P.loc["MLK004", "method"] == forecast.INSUFFICIENT                       # 6 days history
    assert not P.loc["MLK004", "overstock"]                                         # no fake flags
    assert P.loc["YOG004", "confidence"] == "Low"
    assert P.loc["BIS001", "overstock"] and P.loc["GRO003", "overstock"]
    assert P.loc["BIS003", "slow"] and P.loc["GRO005", "slow"]

    recs = pd.DataFrame(A.recs)
    assert recs["rec_key"].is_unique
    types = set(recs["action_type"])
    assert {"Apply 20% discount", "Apply 10% discount", "Prioritise near-expiry stock",
            "Monitor slow-moving product"} <= types
    assert types & {"Reduce next reorder quantity", "Skip next reorder"}
    assert not recs[recs["sku"] == "MLK004"]["action_type"].str.contains("discount|reorder").any()
    disc = recs[recs["action_type"].str.contains("discount")]
    assert disc["rationale"].str.contains("expires").all()
    assert (disc.loc[disc["action_type"].str.contains("20"), "discount_pct"] == 20).all()


def test_fefo_allocation_and_expired(fresh_db):
    # one product, steady 10/day, two batches: early one too big to sell, late one fine
    db.clear_all_data()
    db.add_product("F1", "Fefo", "Milk", 100, 60, 10, 50)
    db.add_batch("F1", 100, (TODAY + timedelta(days=2)).isoformat())      # sells ~30 before expiry
    db.add_batch("F1", 40, (TODAY + timedelta(days=10)).isoformat())
    db.add_batch("F1", 7, (TODAY - timedelta(days=1)).isoformat())        # expired
    sales = pd.DataFrame({"date": [(TODAY - timedelta(days=i)).isoformat() for i in range(1, 41)],
                          "sku": "F1", "units_sold": 10})
    s = validation.validate_sales(sales, ["F1"])
    db.import_sales(s.clean)
    A = run_analysis()
    b = A.batches.set_index("days_to_expiry")
    assert b.loc[-1, "units_at_risk"] == 7
    assert 60 <= b.loc[2, "units_at_risk"] <= 80                          # ~30 of 100 sell in 3 days
    assert b.loc[10, "units_at_risk"] == 0                                # fully sold by day 10
    kinds = {r["action_type"] for r in A.recs}
    assert "Remove expired stock" in kinds and "Apply 20% discount" in kinds


def test_no_expiry_batches_not_at_risk(fresh_db):
    db.clear_all_data()
    db.add_product("R1", "Rice", "Other Grocery", 500, 400, None, 10, quantity=20, expiry_date=None)
    A = run_analysis()
    assert A.batches.iloc[0]["units_at_risk"] == 0 and A.batches.iloc[0]["expiry_level"] == "No expiry"
    assert A.recs == []


def test_settings_change_flags(fresh_db):
    base = run_analysis()
    db.save_settings({"slow_velocity": 5.0})
    s = db.get_settings()
    assert s["slow_velocity"] == 5.0
    assert run_analysis(s).totals["slow"] > base.totals["slow"]


# --------------------------------------------------------- action centre
def test_approval_workflow_and_persistence(fresh_db):
    A = run_analysis()
    db.sync_recommendations(A.recs)
    pend = db.read_recommendations("Pending")
    assert len(pend) == len(A.recs) > 5
    rid = int(pend.iloc[0]["rec_id"])
    rid2 = int(pend.iloc[1]["rec_id"])
    assert db.decide(rid, "Approved", "ok by manager")
    assert db.decide(rid2, "Rejected")
    assert not db.decide(rid, "Rejected")                 # cannot decide twice
    with pytest.raises(ValueError):
        db.decide(rid2, "Maybe")
    db.sync_recommendations(run_analysis().recs)          # re-sync must keep decisions
    allr = db.read_recommendations().set_index("rec_id")
    assert allr.loc[rid, "status"] == "Approved" and allr.loc[rid2, "status"] == "Rejected"
    assert len(db.read_recommendations("Pending")) == len(A.recs) - 2
    log = db.read_action_log()
    assert list(log["decision"]) == ["Rejected", "Approved"] and log.iloc[1]["note"] == "ok by manager"
    # real prices untouched
    assert (db.read_products().set_index("sku")["price"] == A.products.set_index("sku")["price"]).all()
    db.clear_action_history()
    assert db.read_action_log().empty


def test_reset_to_sample_and_exports(fresh_db):
    db.clear_all_data()
    assert db.read_products().empty
    assert analysis.build_analysis(db.read_products(), db.read_batches(), db.read_sales(),
                                   db.get_settings(), TODAY).totals["total_products"] == 0
    db.init_db()
    assert db.read_products().empty                       # does not silently reseed
    db.seed_sample()
    A = run_analysis()
    for df in (A.products, A.batches, pd.DataFrame(A.recs)):
        out = df.to_csv(index=False)
        assert len(pd.read_csv(io.StringIO(out))) == len(df)


def test_sample_csvs_validate():
    inv = validation.validate_inventory(sample_data.sample_inventory_csv().astype(str))
    assert inv.ok, inv.row_errors[:3]
    skus = set(inv.clean["sku"])
    s = validation.validate_sales(sample_data.sample_sales_csv().astype(str), skus)
    assert s.ok, s.row_errors[:3]
    assert validation.validate_inventory(sample_data.template_inventory_csv().astype(str)).ok
    assert validation.validate_sales(sample_data.template_sales_csv().astype(str), ["MLK900", "BIS900"]).ok
