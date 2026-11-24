"""Theme (CSS) and small HTML/Streamlit helpers shared by all pages."""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from . import config

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], .stApp { font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif; }
.stApp { background: #ffffff; color: #14281d; }
.block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1280px; }
#MainMenu, footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }
h1, h2, h3 { color: #14532d; letter-spacing: -0.01em; }
h3 { font-weight: 700; }

/* ---------- sidebar ---------- */
[data-testid="stSidebar"] { background: linear-gradient(180deg, #eaf6ee 0%, #f7fbf8 100%); border-right: 1px solid #d5e9dc; }
[data-testid="stSidebar"] .block-container { padding-top: 1rem; }
.ww-brand { background: linear-gradient(135deg, #14532d 0%, #1f7a4d 100%); color: #fff; border-radius: 16px;
  padding: 16px 16px 14px 16px; margin-bottom: 14px; box-shadow: 0 6px 18px rgba(20,83,45,.25); }
.ww-brand .name { font-size: 1.35rem; font-weight: 800; letter-spacing: -0.02em; }
.ww-brand .tag { font-size: .72rem; opacity: .85; margin-top: 2px; line-height: 1.35; }
[data-testid="stSidebar"] div[role="radiogroup"] { gap: 4px; }
[data-testid="stSidebar"] div[role="radiogroup"] > label { padding: 9px 12px; border-radius: 12px; width: 100%;
  transition: background .15s ease; cursor: pointer; }
[data-testid="stSidebar"] div[role="radiogroup"] > label:hover { background: #d9eee0; }
[data-testid="stSidebar"] div[role="radiogroup"] > label > div:first-child:not(:has(p)) { display: none; }
[data-testid="stSidebar"] div[role="radiogroup"] > label p { font-weight: 600; color: #1d3d2b; font-size: .95rem; }
[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) { background: #14532d; }
[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) p { color: #ffffff; }
.ww-side-note { font-size: .75rem; color: #3d5a47; background: #ffffffaa; border: 1px solid #d5e9dc; border-radius: 12px;
  padding: 10px 12px; margin-top: 10px; line-height: 1.45; }

/* ---------- page header ---------- */
.ww-hero { background: linear-gradient(120deg, #14532d 0%, #1f7a4d 60%, #4fa876 100%); border-radius: 20px; padding: 22px 26px;
  color: #fff; margin-bottom: 18px; box-shadow: 0 8px 24px rgba(20,83,45,.18); }
.ww-hero h1 { color: #fff; margin: 0; font-size: 1.7rem; font-weight: 800; }
.ww-hero p { margin: 4px 0 0 0; opacity: .92; font-size: .95rem; }
.ww-page-title { margin-bottom: 14px; }
.ww-page-title h1 { margin: 0; font-size: 1.6rem; font-weight: 800; color: #14532d; }
.ww-page-title p { margin: 2px 0 0 0; color: #4b6455; font-size: .92rem; }

/* ---------- stat cards ---------- */
.ww-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 14px; margin: 6px 0 18px 0; }
.ww-card { background: #fff; border: 1px solid #dcebe0; border-radius: 16px; padding: 14px 16px 12px 16px;
  box-shadow: 0 2px 10px rgba(20,83,45,.06); position: relative; overflow: hidden; }
.ww-card::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 5px; background: #4fa876; }
.ww-card.warn::before { background: #e8a03a; } .ww-card.danger::before { background: #d64545; }
.ww-card.info::before { background: #6b8fd6; } .ww-card.dark::before { background: #14532d; }
.ww-card .label { font-size: .72rem; text-transform: uppercase; letter-spacing: .06em; color: #5a7364; font-weight: 600; }
.ww-card .value { font-size: 1.85rem; font-weight: 800; color: #14532d; line-height: 1.2; margin-top: 2px; }
.ww-card.warn .value { color: #b9741a; } .ww-card.danger .value { color: #b83232; }
.ww-card .sub { font-size: .78rem; color: #6c8576; margin-top: 2px; }

/* ---------- misc ---------- */
.ww-banner { background: #fff8e6; border: 1px solid #f1d58a; color: #6b4d06; border-radius: 12px; padding: 9px 14px;
  font-size: .85rem; margin-bottom: 14px; }
.ww-banner b { color: #5a3f00; }
.ww-info { background: #eaf6ee; border: 1px solid #cfe6d7; color: #1d3d2b; border-radius: 12px; padding: 10px 14px; font-size: .88rem; margin: 6px 0 12px 0; }
.ww-badge { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: .74rem; font-weight: 700; }
.ww-badge.high { background: #fde4e4; color: #a62b2b; } .ww-badge.medium { background: #fff0d6; color: #9a5d0a; }
.ww-badge.low { background: #e3f1e8; color: #1f6b43; }
.ww-rec-title { font-weight: 700; font-size: 1.02rem; color: #14532d; }
.ww-rec-meta { color: #5a7364; font-size: .8rem; }
.ww-rec-text { font-size: .9rem; color: #243a2e; margin-top: 6px; line-height: 1.5; }
.ww-empty { text-align: center; padding: 40px 20px; border: 2px dashed #cfe6d7; border-radius: 18px; color: #4b6455; background: #f7fbf8; }

.stButton > button, .stDownloadButton > button { border-radius: 10px; font-weight: 600; border: 1px solid #b9d8c4; }
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
  background: #14532d; border-color: #14532d; color: #fff; }
.stButton > button[kind="primary"]:hover { background: #1f7a4d; border-color: #1f7a4d; }
[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 16px; }
button[data-baseweb="tab"] { font-weight: 600; }
[data-testid="stDataFrame"] { border: 1px solid #dcebe0; border-radius: 12px; overflow: hidden; }

@media (max-width: 768px) {
  .block-container { padding-left: 0.9rem; padding-right: 0.9rem; padding-top: 1rem; }
  .ww-hero { padding: 16px 16px; border-radius: 16px; } .ww-hero h1 { font-size: 1.35rem; }
  .ww-cards { grid-template-columns: repeat(2, 1fr); gap: 10px; }
  .ww-card .value { font-size: 1.45rem; }
}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def esc(x) -> str:
    """HTML-escape any value (user data is never trusted inside raw HTML)."""
    return html.escape(str(x))


_e = esc


def inr(x, decimals: int = 0) -> str:
    if x is None or pd.isna(x):
        return "—"
    return f"{config.CURRENCY}{x:,.{decimals}f}"


def brand() -> None:
    st.sidebar.markdown(
        f'<div class="ww-brand"><div class="name">🌿 {config.APP_NAME}</div>'
        f'<div class="tag">{config.TAGLINE}</div></div>', unsafe_allow_html=True)


def hero(title: str, subtitle: str) -> None:
    st.markdown(f'<div class="ww-hero"><h1>{_e(title)}</h1><p>{_e(subtitle)}</p></div>', unsafe_allow_html=True)


def page_title(title: str, subtitle: str = "") -> None:
    sub = f"<p>{_e(subtitle)}</p>" if subtitle else ""
    st.markdown(f'<div class="ww-page-title"><h1>{_e(title)}</h1>{sub}</div>', unsafe_allow_html=True)


def stat_cards(cards: list[dict]) -> None:
    """cards: [{label, value, sub, tone}] where tone in '', warn, danger, info, dark."""
    parts = []
    for c in cards:
        parts.append(
            f'<div class="ww-card {c.get("tone", "")}"><div class="label">{_e(c["label"])}</div>'
            f'<div class="value">{_e(c["value"])}</div><div class="sub">{_e(c.get("sub", ""))}</div></div>')
    st.markdown('<div class="ww-cards">' + "".join(parts) + "</div>", unsafe_allow_html=True)


def info(text: str) -> None:
    st.markdown(f'<div class="ww-info">{_e(text)}</div>', unsafe_allow_html=True)


def sample_banner(products: pd.DataFrame) -> None:
    if products is None or products.empty or "is_sample" not in products:
        return
    n, total = int(products["is_sample"].sum()), len(products)
    if n == 0:
        return
    if n == total:
        msg = ("<b>SAMPLE / SYNTHETIC DATA.</b> All products, sales history, stock and expiry dates on this screen "
               "are generated for demonstration. They are not from a real store.")
    else:
        msg = (f"<b>Includes SAMPLE / SYNTHETIC DATA</b> ({n} of {total} products). "
               "Sample items are not from a real store.")
    st.markdown(f'<div class="ww-banner">🧪 {msg}</div>', unsafe_allow_html=True)


def empty_state(title: str, text: str) -> None:
    st.markdown(f'<div class="ww-empty"><h3 style="margin:0 0 6px 0">{_e(title)}</h3><div>{_e(text)}</div></div>',
                unsafe_allow_html=True)


def badge(priority: str) -> str:
    return f'<span class="ww-badge {esc(priority).lower()}">{esc(priority)} priority</span>'


def reset_if_stale(key: str, options) -> None:
    """Drop a remembered selectbox value that is no longer one of the options (e.g. product deleted)."""
    if key in st.session_state and st.session_state[key] not in list(options):
        del st.session_state[key]


def goto(page: str) -> None:
    """on_click callback: switch the sidebar navigation."""
    st.session_state["nav"] = page


def csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def table(df: pd.DataFrame, column_config: dict | None = None, height: int | None = None) -> None:
    kwargs = dict(use_container_width=True, hide_index=True)
    if column_config:
        kwargs["column_config"] = column_config
    if height:
        kwargs["height"] = height
    st.dataframe(df, **kwargs)


def money_col(label: str, decimals: int = 0):
    return st.column_config.NumberColumn(label, format=f"{config.CURRENCY}%.{decimals}f")
