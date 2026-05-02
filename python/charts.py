"""
NEPSE B58 Analysis — Charts Module
=====================================
All Plotly chart generation functions.
Each function returns a plotly.graph_objects.Figure.
"""

import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from config import COLORS, PLOTLY_LAYOUT, ACTION_COLORS, SECTOR_COLORS


def _base(title: str = "", **kwargs) -> dict:
    """Return base layout merged with title and any overrides."""
    import copy
    layout = copy.deepcopy(PLOTLY_LAYOUT)
    if title:
        layout["title"] = dict(text=title, font=dict(color=COLORS["text"], size=13), x=0.01)
    # Merge nested dicts (xaxis, yaxis) rather than replacing
    for k, v in kwargs.items():
        if k in layout and isinstance(layout[k], dict) and isinstance(v, dict):
            layout[k] = {**layout[k], **v}
        else:
            layout[k] = v
    return layout


# ── OVERVIEW CHARTS ───────────────────────────────────────────────────────────

def chart_nepse_trend(market_df: pd.DataFrame) -> go.Figure:
    """NEPSE close price trend with color-coded markers."""
    df = market_df.copy()
    colors = [COLORS["green"] if c else COLORS["red"]
              for c in df["nepse_close"].diff().fillna(0) >= 0]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["nepse_close"],
        mode="lines+markers",
        line=dict(color=COLORS["accent"], width=2.5),
        marker=dict(size=7, color=colors, line=dict(width=1, color=COLORS["bg2"])),
        fill="tozeroy",
        fillcolor=f"rgba(240,180,41,0.05)",
        name="NEPSE Close",
        hovertemplate="<b>%{x|%b %d}</b><br>Close: %{y:,.2f}<extra></extra>",
    ))
    # Add 5-day MA
    df["ma5"] = df["nepse_close"].rolling(3).mean()
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["ma5"],
        mode="lines", line=dict(color=COLORS["blue"], width=1.5, dash="dot"),
        name="3-Day MA", opacity=0.7,
        hovertemplate="%{y:,.2f}<extra>3D MA</extra>",
    ))
    fig.update_layout(**_base("NEPSE Index — Daily Close",
                              yaxis=dict(tickformat=",.0f")))
    return fig


def chart_turnover(market_df: pd.DataFrame) -> go.Figure:
    """Daily turnover bar chart."""
    df = market_df.copy()
    avg = df["turnover_b"].mean()
    colors = [COLORS["green"] if t >= avg else COLORS["amber"] if t >= avg * 0.8
              else COLORS["red"] for t in df["turnover_b"]]

    fig = go.Figure(go.Bar(
        x=df["date"], y=df["turnover_b"],
        marker_color=colors, name="Turnover",
        hovertemplate="<b>%{x|%b %d}</b><br>₨%{y:.2f}B<extra></extra>",
    ))
    fig.add_hline(y=avg, line_dash="dot", line_color=COLORS["muted"],
                  annotation_text=f"Avg: ₨{avg:.2f}B",
                  annotation_font_color=COLORS["muted"])
    fig.update_layout(**_base("Daily Turnover (Rs. Billion)", yaxis=dict(ticksuffix="B")))
    return fig


def chart_b58_net_vs_nepse(market_df: pd.DataFrame) -> go.Figure:
    """Dual-axis: B58 net flow bars + NEPSE line."""
    df = market_df.copy()
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    colors = [f"rgba(63,185,80,0.8)" if v >= 0 else f"rgba(248,81,73,0.8)"
              for v in df["b58_net_m"]]
    fig.add_trace(go.Bar(
        x=df["date"], y=df["b58_net_m"], name="B58 Net (Rs.M)",
        marker_color=colors,
        hovertemplate="<b>%{x|%b %d}</b><br>₨%{y:.1f}M<extra>B58 Net</extra>",
    ), secondary_y=False)

    fig.add_trace(go.Scatter(
        x=df["date"], y=df["nepse_close"], mode="lines",
        line=dict(color=COLORS["blue"], width=2.5),
        name="NEPSE", yaxis="y2",
        hovertemplate="%{y:,.2f}<extra>NEPSE</extra>",
    ), secondary_y=True)

    fig.update_layout(**_base("B58 Net Flow vs NEPSE Close"))
    fig.update_yaxes(title_text="B58 Net (Rs.M)", secondary_y=False, gridcolor=COLORS["bg3"])
    fig.update_yaxes(title_text="NEPSE Close", secondary_y=True, gridcolor="rgba(0,0,0,0)", tickformat=",.0f")
    return fig


def chart_advance_decline(market_df: pd.DataFrame) -> go.Figure:
    """Advance/Decline bar chart."""
    df = market_df.copy()
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["date"], y=df["advance"], name="Advance",
        marker_color="rgba(63,185,80,0.75)",
        hovertemplate="<b>%{x|%b %d}</b><br>Advance: %{y}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=df["date"], y=-df["decline"], name="Decline",
        marker_color="rgba(248,81,73,0.75)",
        hovertemplate="<b>%{x|%b %d}</b><br>Decline: %{y}<extra></extra>",
    ))
    fig.update_layout(**_base("Advance / Decline Balance", yaxis=dict(title="Stocks")), barmode="overlay")
    return fig


# ── SIGNAL CHARTS ─────────────────────────────────────────────────────────────

def chart_action_donut(tech_df: pd.DataFrame) -> go.Figure:
    """Action distribution donut for latest day."""
    latest = tech_df[tech_df["date"] == tech_df["date"].max()]
    cnt = latest["action_grp"].value_counts().reset_index()
    cnt.columns = ["action", "count"]

    fig = go.Figure(go.Pie(
        labels=cnt["action"], values=cnt["count"],
        hole=0.55,
        marker_colors=[ACTION_COLORS.get(a, COLORS["muted"]) for a in cnt["action"]],
        textfont_color=COLORS["text"],
        textinfo="label+percent",
        hovertemplate="<b>%{label}</b><br>%{value} symbols (%{percent})<extra></extra>",
    ))
    layout = _base("Action Distribution — Latest Session")
    layout["showlegend"] = False
    layout["margin"] = dict(t=40, r=10, b=10, l=10)
    fig.update_layout(**layout)
    return fig


def chart_rsi_distribution(tech_df: pd.DataFrame) -> go.Figure:
    """RSI histogram by action group."""
    latest = tech_df[tech_df["date"] == tech_df["date"].max()]
    fig = go.Figure()
    for action, color in [("BUY/ADD", COLORS["green"]), ("HOLD", COLORS["blue"]),
                           ("WATCH", COLORS["amber"]), ("AVOID", COLORS["red"])]:
        subset = latest[latest["action_grp"] == action]
        if len(subset):
            fig.add_trace(go.Histogram(
                x=subset["rsi"], name=action, nbinsx=8,
                marker_color=color, opacity=0.75,
                hovertemplate="RSI %{x:.0f}–%{x:.0f}<br>Count: %{y}<extra>"+action+"</extra>",
            ))
    fig.add_vline(x=35, line_dash="dash", line_color=COLORS["red"],
                  annotation_text="Oversold 35", annotation_font_color=COLORS["red"])
    fig.add_vline(x=55, line_dash="dash", line_color=COLORS["green"],
                  annotation_text="Strong 55", annotation_font_color=COLORS["green"])
    fig.update_layout(**_base("RSI Distribution by Signal"), barmode="overlay", xaxis_title="RSI", yaxis_title="Count")
    return fig


def chart_rsi_adx_matrix(tech_df: pd.DataFrame) -> go.Figure:
    """RSI × ADX scatter matrix with ATR as bubble size."""
    latest = tech_df[tech_df["date"] == tech_df["date"].max()]
    fig = go.Figure()

    for action, color in [("BUY/ADD", COLORS["green"]), ("HOLD", COLORS["blue"]),
                           ("WATCH", COLORS["amber"]), ("AVOID", COLORS["red"])]:
        sub = latest[latest["action_grp"] == action]
        if len(sub):
            fig.add_trace(go.Scatter(
                x=sub["rsi"], y=sub["adx"],
                mode="markers+text",
                marker=dict(
                    size=sub["atr"].clip(6, 50),
                    color=color, opacity=0.8,
                    line=dict(width=1, color=COLORS["bg2"]),
                ),
                text=sub["sym"], textposition="top center",
                textfont=dict(size=9, color=COLORS["muted"]),
                name=action,
                hovertemplate="<b>%{text}</b><br>RSI: %{x:.1f}<br>ADX: %{y:.1f}<br>ATR: %{marker.size:.1f}<extra>"+action+"</extra>",
            ))

    # Zone annotations
    fig.add_vrect(x0=0, x1=35, fillcolor="rgba(248,81,73,0.06)", line_width=0,
                  annotation_text="Oversold", annotation_position="top left",
                  annotation_font_color=COLORS["red"])
    fig.add_vrect(x0=55, x1=80, fillcolor="rgba(63,185,80,0.06)", line_width=0,
                  annotation_text="Bullish Zone", annotation_position="top right",
                  annotation_font_color=COLORS["green"])
    fig.add_hline(y=20, line_dash="dot", line_color=COLORS["muted"],
                  annotation_text="Trending >20", annotation_font_color=COLORS["muted"])

    fig.update_layout(**_base("RSI × ADX Momentum Matrix (Size = ATR)", xaxis=dict(title="RSI (Momentum)", range=[20, 70]), yaxis=dict(title="ADX (Trend Strength)")))
    return fig


def chart_rsi_heatmap(tech_df: pd.DataFrame) -> go.Figure:
    """RSI heatmap: symbols × dates."""
    pivot = tech_df.pivot_table(index="sym", columns="date", values="rsi", aggfunc="first")
    pivot.columns = [d.strftime("%b %d") for d in pivot.columns]

    # Custom colorscale: red→yellow→green
    colorscale = [
        [0.0,  "#7b1a1a"],
        [0.35, "#7b1a1a"],
        [0.35, "#5a4a00"],
        [0.55, "#5a4a00"],
        [0.55, "#0d4a1e"],
        [1.0,  "#1a6b32"],
    ]

    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=pivot.columns.tolist(),
        y=pivot.index.tolist(),
        colorscale=colorscale,
        zmin=20, zmax=80,
        colorbar=dict(title="RSI", tickfont=dict(color=COLORS["muted"], size=10)),
        hovertemplate="<b>%{y}</b> — %{x}<br>RSI: %{z:.1f}<extra></extra>",
    ))
    _hl = _base("RSI Heatmap — All Symbols × All Sessions")
    _hl["yaxis"] = dict(tickfont=dict(size=10), gridcolor=COLORS["bg3"])
    _hl["xaxis"] = dict(side="bottom", tickfont=dict(size=10), gridcolor=COLORS["border"])
    fig.update_layout(**_hl, height=max(350, len(pivot) * 22 + 80))
    return fig


def chart_rsi_trend_lines(tech_df: pd.DataFrame, top_n: int = 8) -> go.Figure:
    """RSI trend lines for top-N most tracked symbols."""
    # Pick symbols that appear most often
    top_syms = (tech_df.groupby("sym").size()
                .sort_values(ascending=False).head(top_n).index.tolist())
    df = tech_df[tech_df["sym"].isin(top_syms)].copy()

    fig = go.Figure()
    for sym in top_syms:
        sub = df[df["sym"] == sym].sort_values("date")
        fig.add_trace(go.Scatter(
            x=sub["date"], y=sub["rsi"], mode="lines+markers",
            name=sym, line=dict(width=2), marker=dict(size=5),
            hovertemplate="<b>"+sym+"</b><br>%{x|%b %d}<br>RSI: %{y:.1f}<extra></extra>",
        ))

    fig.add_hrect(y0=55, y1=80, fillcolor="rgba(63,185,80,0.05)", line_width=0)
    fig.add_hrect(y0=0, y1=35, fillcolor="rgba(248,81,73,0.05)", line_width=0)
    fig.add_hline(y=35, line_dash="dash", line_color=COLORS["red"], opacity=0.4)
    fig.add_hline(y=55, line_dash="dash", line_color=COLORS["green"], opacity=0.4)

    fig.update_layout(**_base(f"RSI Trend — Top {top_n} Symbols", yaxis=dict(title="RSI", range=[15, 75])))
    return fig


# ── B58 CHARTS ────────────────────────────────────────────────────────────────

def chart_b58_daily_net(market_df: pd.DataFrame) -> go.Figure:
    """B58 net buy/sell bars with cumulative line."""
    df = market_df.copy()
    colors = [f"rgba(63,185,80,0.85)" if v >= 0 else "rgba(248,81,73,0.85)"
              for v in df["b58_net_m"]]
    cum = df["b58_net_m"].cumsum()

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(
        x=df["date"], y=df["b58_net_m"],
        marker_color=colors, name="Daily Net",
        text=[f"{'+'if v>=0 else ''}{v:.0f}M" for v in df["b58_net_m"]],
        textposition="outside", textfont=dict(size=9, color=COLORS["muted"]),
        hovertemplate="<b>%{x|%b %d}</b><br>₨%{y:.1f}M<extra>Daily Net</extra>",
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=df["date"], y=cum, mode="lines",
        line=dict(color=COLORS["purple"], width=2, dash="dot"),
        name="Cumulative", yaxis="y2",
        hovertemplate="Cumulative: ₨%{y:.1f}M<extra></extra>",
    ), secondary_y=True)

    fig.update_layout(**_base("B58 Net Buy/Sell — Daily (Rs.M)"))
    fig.update_yaxes(title_text="Daily Net (Rs.M)", secondary_y=False, gridcolor=COLORS["bg3"])
    fig.update_yaxes(title_text="Cumulative (Rs.M)", secondary_y=True, gridcolor="rgba(0,0,0,0)")
    return fig


def chart_b58_market_share(b58_df: pd.DataFrame, top_n: int = 10) -> go.Figure:
    """Average B58 market share % per symbol."""
    agg = (b58_df[b58_df["buy_mkt_pct"] > 0]
           .groupby("sym")["buy_mkt_pct"]
           .mean()
           .sort_values(ascending=False)
           .head(top_n)
           .reset_index())
    agg.columns = ["sym", "avg_mkt_pct"]

    colors = [COLORS["accent"] if v >= 30 else COLORS["green"] if v >= 15
              else COLORS["blue"] for v in agg["avg_mkt_pct"]]

    fig = go.Figure(go.Bar(
        x=agg["sym"], y=agg["avg_mkt_pct"],
        marker_color=colors,
        text=[f"{v:.1f}%" for v in agg["avg_mkt_pct"]],
        textposition="outside", textfont=dict(size=10, color=COLORS["text"]),
        hovertemplate="<b>%{x}</b><br>Avg Market Share: %{y:.1f}%<extra></extra>",
    ))
    fig.update_layout(**_base(f"B58 Avg Market Share % — Top {top_n} Symbols", yaxis=dict(title="Avg Mkt %", ticksuffix="%")))
    return fig


def chart_b58_cumulative_net(b58_df: pd.DataFrame, top_n: int = 6) -> go.Figure:
    """Cumulative net kitta over time for top symbols."""
    top_syms = (b58_df.groupby("sym")["net_kitta"].sum()
                .sort_values(ascending=False).head(top_n).index.tolist())

    fig = go.Figure()
    for sym in top_syms:
        sub = b58_df[b58_df["sym"] == sym].sort_values("date").copy()
        sub["cum_net"] = sub["net_kitta"].cumsum()
        fig.add_trace(go.Scatter(
            x=sub["date"], y=sub["cum_net"],
            mode="lines+markers", name=sym,
            line=dict(width=2.5), marker=dict(size=5),
            hovertemplate="<b>"+sym+"</b><br>%{x|%b %d}<br>Cum Net: %{y:,}<extra></extra>",
        ))

    fig.add_hline(y=0, line_dash="dot", line_color=COLORS["border"])
    fig.update_layout(**_base(f"Cumulative Net Kitta — Top {top_n} Symbols", yaxis=dict(title="Net Kitta (Cumulative)")))
    return fig


def chart_b58_buy_sell(b58_df: pd.DataFrame, top_n: int = 10) -> go.Figure:
    """Total buy vs sell kitta per symbol."""
    agg = (b58_df.groupby("sym")
           .agg(total_buy=("buy_kitta", "sum"), total_sell=("sell_kitta", "sum"))
           .reset_index()
           .assign(net=lambda x: x["total_buy"] - x["total_sell"])
           .sort_values("total_buy", ascending=False)
           .head(top_n))

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=agg["sym"], y=agg["total_buy"], name="Total Buy",
        marker_color="rgba(63,185,80,0.8)",
        hovertemplate="<b>%{x}</b><br>Buy: %{y:,}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=agg["sym"], y=-agg["total_sell"], name="Total Sell",
        marker_color="rgba(248,81,73,0.8)",
        hovertemplate="<b>%{x}</b><br>Sell: %{y:,}<extra></extra>",
    ))
    fig.update_layout(**_base(f"B58 Total Buy vs Sell Kitta — Top {top_n}", yaxis=dict(title="Kitta")), barmode="group")
    return fig


# ── CONVICTION CHARTS ─────────────────────────────────────────────────────────

def chart_conviction_scores(conv_df: pd.DataFrame, top_n: int = 15) -> go.Figure:
    """Conviction score horizontal bar chart."""
    top = conv_df.head(top_n).sort_values("conviction_score")
    colors = [COLORS["accent"] if s >= 80 else COLORS["green"] if s >= 60
              else COLORS["blue"] if s >= 40 else COLORS["muted"]
              for s in top["conviction_score"]]

    fig = go.Figure(go.Bar(
        x=top["conviction_score"], y=top["sym"],
        orientation="h", marker_color=colors,
        text=[f"{s:.0f}" for s in top["conviction_score"]],
        textposition="outside", textfont=dict(size=10, color=COLORS["text"]),
        hovertemplate="<b>%{y}</b><br>Score: %{x:.1f}<extra></extra>",
    ))
    fig.add_vline(x=60, line_dash="dash", line_color=COLORS["green"],
                  annotation_text="Buy Zone", annotation_font_color=COLORS["green"])
    fig.add_vline(x=80, line_dash="dash", line_color=COLORS["accent"],
                  annotation_text="High Conv.", annotation_font_color=COLORS["accent"])
    fig.update_layout(**_base(f"B58 Conviction Score — Top {top_n} Symbols", xaxis=dict(title="Score", range=[0, 105])), height=max(350, top_n * 28 + 80))
    return fig


def chart_buy_streak(conv_df: pd.DataFrame, top_n: int = 12) -> go.Figure:
    """Consecutive buy streak bar chart."""
    top = conv_df[conv_df["buy_streak"] > 0].head(top_n).sort_values("buy_streak", ascending=False)
    colors = [COLORS["accent"] if s >= 8 else COLORS["green"] if s >= 5
              else COLORS["blue"] if s >= 3 else COLORS["muted"]
              for s in top["buy_streak"]]

    fig = go.Figure(go.Bar(
        x=top["sym"], y=top["buy_streak"],
        marker_color=colors,
        text=[f"{s}d 🔥" if s >= 3 else f"{s}d" for s in top["buy_streak"]],
        textposition="outside", textfont=dict(size=11, color=COLORS["text"]),
        hovertemplate="<b>%{x}</b><br>%{y} consecutive buy days<extra></extra>",
    ))
    fig.update_layout(**_base("Consecutive Buy Streak (Days)", yaxis=dict(title="Days", dtick=1)))
    return fig


def chart_entry_vs_ltp(conv_df: pd.DataFrame, tech_df: pd.DataFrame) -> go.Figure:
    """B58 avg entry price vs current LTP."""
    latest_ltp = (tech_df[tech_df["date"] == tech_df["date"].max()]
                  .set_index("sym")["ltp"].to_dict())

    df = conv_df[conv_df["avg_buy_price"] > 0].copy()
    df["current_ltp"] = df["sym"].map(latest_ltp)
    df = df.dropna(subset=["current_ltp"]).head(10)
    df["pnl_pct"] = ((df["current_ltp"] - df["avg_buy_price"]) / df["avg_buy_price"] * 100).round(1)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["sym"], y=df["avg_buy_price"], name="B58 Avg Entry",
        marker_color="rgba(88,166,255,0.75)",
        hovertemplate="<b>%{x}</b><br>Avg Entry: ₨%{y:,.2f}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=df["sym"], y=df["current_ltp"], name="Current LTP",
        marker_color="rgba(240,180,41,0.75)",
        hovertemplate="<b>%{x}</b><br>LTP: ₨%{y:,.2f}<extra></extra>",
    ))
    fig.update_layout(**_base("B58 Avg Entry Price vs Current LTP", yaxis=dict(title="Price (Rs.)")), barmode="group")
    return fig


# ── MOMENTUM CHARTS ───────────────────────────────────────────────────────────

def chart_price_change(tech_df: pd.DataFrame) -> go.Figure:
    """Price % change from first to last available session."""
    from analysis import get_price_momentum
    df = get_price_momentum(tech_df).sort_values("chg_pct", ascending=False)
    colors = [COLORS["green"] if v >= 0 else COLORS["red"] for v in df["chg_pct"]]

    fig = go.Figure(go.Bar(
        x=df["sym"], y=df["chg_pct"],
        marker_color=colors,
        text=[f"{'+'if v>=0 else ''}{v:.1f}%" for v in df["chg_pct"]],
        textposition="outside", textfont=dict(size=9),
        hovertemplate="<b>%{x}</b><br>%{y:.1f}%<extra></extra>",
    ))
    fig.add_hline(y=0, line_color=COLORS["border"], line_dash="dot")
    fig.update_layout(**_base("Price % Change — First to Latest Session", yaxis=dict(title="% Change", ticksuffix="%")))
    return fig


def chart_rsi_velocity(tech_df: pd.DataFrame) -> go.Figure:
    """Day-over-day RSI change."""
    from analysis import get_rsi_trend
    df = get_rsi_trend(tech_df).sort_values("rsi_velocity", ascending=False)
    colors = [COLORS["green"] if v >= 0 else COLORS["red"] for v in df["rsi_velocity"]]

    fig = go.Figure(go.Bar(
        x=df["sym"], y=df["rsi_velocity"],
        marker_color=colors,
        text=[f"{'+'if v>=0 else ''}{v:.1f}" for v in df["rsi_velocity"]],
        textposition="outside", textfont=dict(size=9),
        hovertemplate="<b>%{x}</b><br>RSI Δ: %{y:+.1f}<extra></extra>",
    ))
    fig.add_hline(y=0, line_color=COLORS["border"])
    fig.update_layout(**_base("RSI Velocity — Day-over-Day Change", yaxis=dict(title="RSI Δ")))
    return fig


def chart_volatility_map(tech_df: pd.DataFrame) -> go.Figure:
    """ATR vs LTP scatter — risk/reward positioning."""
    latest = tech_df[tech_df["date"] == tech_df["date"].max()].copy()
    latest["atr_pct"] = (latest["atr"] / latest["ltp"] * 100).round(2)

    fig = go.Figure(go.Scatter(
        x=latest["ltp"], y=latest["atr"],
        mode="markers+text",
        text=latest["sym"],
        textposition="top center",
        textfont=dict(size=9, color=COLORS["muted"]),
        marker=dict(
            size=12,
            color=[ACTION_COLORS.get(a, COLORS["muted"]) for a in latest["action"]],
            opacity=0.85,
            line=dict(width=1, color=COLORS["bg2"]),
        ),
        hovertemplate="<b>%{text}</b><br>LTP: ₨%{x:,.2f}<br>ATR: %{y:.2f}<extra></extra>",
    ))
    fig.update_layout(**_base("ATR vs LTP — Volatility / Price Map", xaxis=dict(title="LTP (Rs.)"), yaxis=dict(title="ATR (Volatility)")))
    return fig


# ── DECISION ENGINE CHARTS ────────────────────────────────────────────────────

def chart_decision_scores(scores_df: pd.DataFrame, top_n: int = 16) -> go.Figure:
    """Multi-factor score bar chart."""
    top = scores_df.head(top_n)
    colors = [COLORS["accent"] if s >= 75 else COLORS["green"] if s >= 60
              else COLORS["blue"] if s >= 45 else COLORS["amber"] if s >= 30
              else COLORS["red"] for s in top["total_score"]]

    fig = go.Figure(go.Bar(
        x=top["sym"], y=top["total_score"],
        marker_color=colors,
        text=[f"{s:.0f}" for s in top["total_score"]],
        textposition="outside", textfont=dict(size=10, color=COLORS["text"]),
        hovertemplate="<b>%{x}</b><br>Score: %{y:.1f}<br>Decision: %{customdata}<extra></extra>",
        customdata=top["decision"],
    ))
    fig.add_hline(y=75, line_dash="dash", line_color=COLORS["accent"],
                  annotation_text="Strong Buy", annotation_font_color=COLORS["accent"])
    fig.add_hline(y=60, line_dash="dot", line_color=COLORS["green"],
                  annotation_text="Buy Zone", annotation_font_color=COLORS["green"])
    fig.update_layout(**_base("Multi-Factor Decision Score", yaxis=dict(title="Score", range=[0, 105])))
    return fig


# ── SECTOR CHARTS ─────────────────────────────────────────────────────────────

def chart_sector_heatmap(subindex_df: pd.DataFrame) -> go.Figure:
    """Sector performance heatmap."""
    pivot = subindex_df.pivot_table(
        index="name", columns="date", values="chg_pct", aggfunc="first"
    ).fillna(0)
    pivot.columns = [d.strftime("%b %d") for d in pivot.columns]

    fig = go.Figure(go.Heatmap(
        z=pivot.values, x=pivot.columns.tolist(), y=pivot.index.tolist(),
        colorscale=[[0, COLORS["red"]], [0.5, COLORS["bg3"]], [1, COLORS["green"]]],
        zmid=0,
        colorbar=dict(title="Chg%", tickfont=dict(color=COLORS["muted"], size=10)),
        hovertemplate="<b>%{y}</b> — %{x}<br>Chg: %{z:.2f}%<extra></extra>",
    ))
    _sl = _base("Sector Performance Heatmap (% Change)")
    _sl["yaxis"] = dict(tickfont=dict(size=10), gridcolor=COLORS["bg3"])
    fig.update_layout(**_sl, height=400)
    return fig


def chart_sector_cumulative(subindex_df: pd.DataFrame) -> go.Figure:
    """Cumulative sector performance lines."""
    pivot = subindex_df.pivot_table(
        index="date", columns="name", values="chg_pct", aggfunc="first"
    ).fillna(0)
    cum = pivot.cumsum()

    fig = go.Figure()
    for col in cum.columns:
        color = SECTOR_COLORS.get(col, COLORS["muted"])
        fig.add_trace(go.Scatter(
            x=cum.index, y=cum[col], mode="lines", name=col,
            line=dict(color=color, width=2),
            hovertemplate="<b>%{fullData.name}</b><br>%{x|%b %d}<br>Cum: %{y:.2f}%<extra></extra>",
        ))
    fig.add_hline(y=0, line_color=COLORS["border"])
    fig.update_layout(**_base("Cumulative Sector Performance", yaxis=dict(title="Cumulative %", ticksuffix="%")))
    return fig
