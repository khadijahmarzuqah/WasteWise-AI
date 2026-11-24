"""Plotly figures (consistent green palette)."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from . import config as C

FONT = dict(family="Inter, system-ui, sans-serif", color="#243a2e")
CAT_COLORS = ["#14532d", "#1f7a4d", "#4fa876", "#8fcfa6", "#bfe3cc", "#e8a03a", "#f2c879", "#6b8fd6", "#9aa9a0"]


def _layout(fig, title: str = "", height: int = 340):
    fig.update_layout(
        title=dict(text=title, font=dict(size=15, color=C.GREEN_DARK), x=0.0, xanchor="left"),
        height=height, margin=dict(l=10, r=10, t=48, b=10), font=FONT,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=-0.28, x=0),
        hoverlabel=dict(font=dict(family=FONT["family"])),
    )
    fig.update_xaxes(showgrid=False, linecolor="#cfe0d5")
    fig.update_yaxes(gridcolor="#e8f0ea", zeroline=False)
    return fig


def forecast_chart(df: pd.DataFrame, title: str = "Demand forecast vs actual sales") -> go.Figure:
    fig = go.Figure()
    styles = {
        "Actual sales": dict(color=C.GREEN_DARK, width=3, dash="solid"),
        "Back-test prediction": dict(color=C.AMBER, width=2.5, dash="dash"),
        "Forecast (next 14 days)": dict(color=C.GREEN_MID, width=3, dash="dot"),
    }
    for name, st_ in styles.items():
        d = df[df["series"] == name]
        if len(d):
            fig.add_trace(go.Scatter(x=d["date"], y=d["units"], name=name, mode="lines",
                                     line=st_, hovertemplate="%{x|%d %b}: %{y:,.0f} units<extra>" + name + "</extra>"))
    fig = _layout(fig, title)
    fig.update_yaxes(title_text="Units / day")
    return fig


def category_donut(products: pd.DataFrame) -> go.Figure:
    g = products.groupby("category", as_index=False)["quantity"].sum().sort_values("quantity", ascending=False)
    fig = go.Figure(go.Pie(labels=g["category"], values=g["quantity"], hole=0.58, sort=False,
                           marker=dict(colors=CAT_COLORS[: len(g)], line=dict(color="#fff", width=2)),
                           textinfo="percent", hovertemplate="%{label}: %{value:,} units (%{percent})<extra></extra>"))
    fig = _layout(fig, "Inventory by category (units)", 340)
    fig.update_layout(legend=dict(orientation="v", y=0.5, x=1.0))
    return fig


def expiry_buckets(batches: pd.DataFrame) -> go.Figure:
    order = ["Expired", "0–3 days", "4–7 days", "8–15 days", "16–30 days", "30+ days"]
    colors = ["#7a1f1f", C.RED, C.AMBER, "#f2d36b", C.GREEN_MID, C.GREEN_SOFT]
    b = batches[batches["days_to_expiry"].notna()].copy()

    def bucket(d):
        if d < 0: return order[0]
        if d <= 3: return order[1]
        if d <= 7: return order[2]
        if d <= 15: return order[3]
        if d <= 30: return order[4]
        return order[5]
    b["bucket"] = b["days_to_expiry"].map(bucket)
    g = b.groupby("bucket")["quantity"].sum().reindex(order).fillna(0)
    fig = go.Figure(go.Bar(x=order, y=g.values, marker_color=colors,
                           hovertemplate="%{x}: %{y:,} units<extra></extra>"))
    return _layout(fig, "Stock by time to expiry (units)", 340)


def risk_by_category(batches: pd.DataFrame) -> go.Figure:
    g = batches.groupby("category")["value_at_risk"].sum().sort_values(ascending=True)
    fig = go.Figure(go.Bar(y=g.index, x=g.values, orientation="h", marker_color=C.AMBER,
                           hovertemplate="%{y}: " + C.CURRENCY + "%{x:,.0f}<extra></extra>"))
    fig = _layout(fig, f"Estimated waste risk by category ({C.CURRENCY})", 340)
    fig.update_xaxes(showgrid=True, gridcolor="#e8f0ea")
    fig.update_yaxes(showgrid=False)
    return fig


def stock_vs_demand(products: pd.DataFrame, top: int = 12) -> go.Figure:
    d = products[products["forecast_14d"].notna() & (products["quantity"] > 0)].copy()
    d["ratio"] = d["quantity"] / d["forecast_14d"].clip(lower=0.1)
    d = d.sort_values("ratio", ascending=False).head(top).iloc[::-1]
    fig = go.Figure()
    fig.add_trace(go.Bar(y=d["name"], x=d["quantity"], name="Stock on hand", orientation="h", marker_color=C.GREEN_DARK))
    fig.add_trace(go.Bar(y=d["name"], x=d["forecast_14d"], name="Forecast demand (14 days)", orientation="h",
                         marker_color=C.GREEN_SOFT))
    fig = _layout(fig, "Stock vs forecast demand – most over-stocked first", max(320, 28 * len(d) + 120))
    fig.update_layout(barmode="group")
    fig.update_yaxes(showgrid=False)
    return fig
