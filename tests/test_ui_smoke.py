"""UI smoke test with lightweight stand-ins for `streamlit` and `plotly`.

This executes every page's Python code path against the real database and
analysis layer (catching NameErrors, wrong column names, bad data handling,
HTML-in-markdown mistakes, ...). It does NOT test Streamlit's own behaviour or
how anything looks - run the real app for that.
"""
import importlib
import sys
import types
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class Rerun(Exception):
    pass


class _State(dict):
    __getattr__ = dict.get

    def __setattr__(self, k, v):
        self[k] = v


class Fake:
    """Context manager / callable / iterable chameleon."""
    def __getattr__(self, name):
        return Fake()

    def __call__(self, *a, **k):
        return Fake()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        return iter([Fake(), Fake(), Fake(), Fake()])


class FakeStreamlit(types.ModuleType):
    def __init__(self, uploads=None, clicks=(), submits=()):
        super().__init__("streamlit")
        self.session_state = _State()
        self.sidebar = self
        self.uploads = uploads or {}
        self.clicks, self.submits = set(clicks), set(submits)
        self.markdown_calls, self.tables, self.errors = [], [], []
        self.column_config = Fake()

    # --- decorators
    def cache_data(self, *a, **k):
        return (lambda f: f) if not (a and callable(a[0])) else a[0]
    cache_resource = cache_data

    # --- layout
    def columns(self, spec, **k):
        n = spec if isinstance(spec, int) else len(spec)
        return [self for _ in range(n)]

    def tabs(self, labels):
        return [self for _ in labels]

    def container(self, **k): return self
    def expander(self, *a, **k): return self
    def form(self, *a, **k): return self
    def __enter__(self): return self
    def __exit__(self, *a): return False

    # --- inputs
    def selectbox(self, label, options, index=0, key=None, **k):
        options = list(options)
        if key in self.session_state and self.session_state[key] in options:
            return self.session_state[key]
        return options[index] if options else None

    def radio(self, label, options, index=0, key=None, **k):
        return self.selectbox(label, options, index, key)

    def multiselect(self, label, options, default=None, **k): return list(default or [])
    def text_input(self, label, value="", **k): return value
    def number_input(self, label, min_value=None, value=0, **k): return value if value is not None else (min_value or 0)
    def checkbox(self, label, value=False, key=None, **k): return key in self.clicks or value
    def toggle(self, *a, value=False, **k): return value
    def date_input(self, label, value=None, **k): return value or date.today()

    def button(self, label, key=None, **k): return key in self.clicks
    def form_submit_button(self, label, **k): return label in self.submits
    def download_button(self, label, data, *a, **k):
        assert isinstance(data, (bytes, str)) and len(data) > 0, label
        return False

    def file_uploader(self, label, key=None, **k): return self.uploads.get(key)

    # --- output
    def markdown(self, body, unsafe_allow_html=False, **k):
        self.markdown_calls.append((body, unsafe_allow_html))

    def dataframe(self, df, column_config=None, **k):
        assert isinstance(df, pd.DataFrame)
        self.tables.append(df)
        if column_config:
            missing = [c for c in column_config if c not in df.columns]
            assert not missing, f"column_config refers to missing columns {missing}; have {list(df.columns)}"

    def error(self, msg, *a, **k): self.errors.append(str(msg))
    def rerun(self): raise Rerun()
    def set_page_config(self, **k): pass

    def __getattr__(self, name):          # st.metric, st.caption, st.write, st.plotly_chart, ...
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: Fake()


@pytest.fixture()
def app_env(tmp_path, monkeypatch):
    from core import config
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "ui.db")

    def make(**kw):
        for m in [m for m in sys.modules if m.split(".")[0] in ("views", "streamlit", "plotly", "app")
                  or m in ("core.ui", "core.charts")]:
            del sys.modules[m]
        import core
        for attr in ("ui", "charts"):          # drop stale submodule attributes bound to an old fake
            if hasattr(core, attr):
                delattr(core, attr)
        fake = FakeStreamlit(**kw)
        sys.modules["streamlit"] = fake
        plotly = types.ModuleType("plotly")
        go = Fake()
        plotly.graph_objects = go
        sys.modules["plotly"], sys.modules["plotly.graph_objects"] = plotly, go
        from core import db
        db.init_db()
        return fake
    yield make
    for m in ("streamlit", "plotly", "plotly.graph_objects"):
        sys.modules.pop(m, None)


def _ctx():
    from types import SimpleNamespace
    from core import analysis, db
    s = db.get_settings()
    A = analysis.build_analysis(db.read_products(), db.read_batches(), db.read_sales(), s, date.today())
    return SimpleNamespace(analysis=A, settings=s, today=date.today())


PAGES = ["dashboard", "inventory", "expiry", "forecasting", "actions", "data_management", "reports", "settings_page"]


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_with_sample_data(app_env, page):
    st = app_env()
    from core import db
    db.sync_recommendations(_ctx().analysis.recs)
    importlib.import_module(f"views.{page}").render(_ctx())
    assert not st.errors


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_with_empty_database(app_env, page):
    st = app_env()
    from core import db
    db.clear_all_data()
    importlib.import_module(f"views.{page}").render(_ctx())


def test_html_blocks_are_markdown_safe(app_env):
    """Indented lines / blank lines inside raw HTML would turn into code blocks in Streamlit markdown."""
    st = app_env()
    from core import db
    db.sync_recommendations(_ctx().analysis.recs)
    for p in PAGES:
        importlib.import_module(f"views.{p}").render(_ctx())
    html = [b for b, unsafe in st.markdown_calls if unsafe and "<div" in b and "<style" not in b]
    assert html
    for b in html:
        assert "\n" not in b, b[:80]


def test_action_centre_approve_reject_buttons(app_env):
    st = app_env()
    from core import db
    db.sync_recommendations(_ctx().analysis.recs)
    pend = db.read_recommendations("Pending")
    first, second = int(pend.iloc[0]["rec_id"]), int(pend.iloc[1]["rec_id"])
    st.clicks = {f"ok_{first}", f"no_{second}"}
    mod = importlib.import_module("views.actions")
    with pytest.raises(Rerun):
        mod.render(_ctx())
    # both buttons are rendered; the first click triggers rerun immediately, run again for the second
    st.clicks = {f"no_{second}"}
    with pytest.raises(Rerun):
        mod.render(_ctx())
    allr = db.read_recommendations().set_index("rec_id")
    assert allr.loc[first, "status"] == "Approved" and allr.loc[second, "status"] == "Rejected"
    st.clicks = set()
    mod.render(_ctx())
    assert len(db.read_action_log()) == 2


class Upload:
    def __init__(self, text): self._b = text.encode()
    def getvalue(self): return self._b


def test_inventory_and_sales_upload_flow(app_env):
    d = lambda n: (date.today() + timedelta(days=n)).isoformat()
    inv = ("sku,name,category,price,quantity,expiry_date\n"
           f"U1,Upload Milk,Milk,60,100,{d(3)}\nU2,Bad Row,Milk,abc,5,{d(3)}\n")
    st = app_env(uploads={"up_inv": Upload(inv)})
    mod = importlib.import_module("views.data_management")
    mod.render(_ctx())
    assert any("Problem" in t.columns for t in st.tables)          # error table shown
    # partial import ticked + import clicked
    st.clicks = {"ok_partial_inv", "do_inv"}
    st.radio_override = None
    st.session_state["inv_mode"] = "Replace ALL inventory (removes products not in the file and their sales)"
    with pytest.raises(Rerun):
        mod.render(_ctx())
    from core import db
    assert list(db.read_products()["sku"]) == ["U1"]
    # sales upload for U1
    rows = "date,sku,units_sold\n" + "".join(f"{(date.today() - timedelta(days=i)).isoformat()},U1,{20 + i % 4}\n" for i in range(1, 35))
    st.uploads = {"up_sales": Upload(rows)}
    st.clicks = {"do_sales"}
    with pytest.raises(Rerun):
        mod.render(_ctx())
    assert len(db.read_sales()) == 34
    A = _ctx().analysis
    assert A.forecasts["U1"].available


def test_bad_files_show_friendly_errors(app_env):
    st = app_env(uploads={"up_inv": Upload("sku,name\nA,B\n")})
    mod = importlib.import_module("views.data_management")
    mod.render(_ctx())
    assert any("Missing required column" in e for e in st.errors)
    st.uploads = {"up_inv": Upload("")}
    st.errors.clear()
    mod.render(_ctx())
    assert any("empty" in e.lower() for e in st.errors)


def test_inventory_add_edit_delete_forms(app_env):
    st = app_env(submits={"Add product"})
    from core import db
    mod = importlib.import_module("views.inventory")
    # fake text inputs return "" -> required-field validation message, no crash, no insert
    n = len(db.read_products())
    mod.render(_ctx())
    assert len(db.read_products()) == n and any("required" in e for e in st.errors)
    st.clicks = {"del_ok_MLK001", "del_btn_MLK001"}
    st.session_state["edit_sku"] = "MLK001"
    with pytest.raises(Rerun):
        mod.render(_ctx())
    assert not db.sku_exists("MLK001")
