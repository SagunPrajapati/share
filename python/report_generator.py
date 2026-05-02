"""
NEPSE B58 Analysis — HTML Report Generator
============================================
Assembles all charts and tables into a single
self-contained HTML dashboard file.
"""

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from typing import Dict
from config import COLORS
from analysis import (
    compute_decision_scores, compute_b58_conviction,
    get_rsi_trend, detect_market_regime, get_sector_momentum,
    compute_b58_nepse_correlation,
)
from charts import (
    chart_nepse_trend, chart_turnover, chart_b58_net_vs_nepse,
    chart_advance_decline, chart_action_donut, chart_rsi_distribution,
    chart_rsi_adx_matrix, chart_rsi_heatmap, chart_rsi_trend_lines,
    chart_b58_daily_net, chart_b58_market_share, chart_b58_cumulative_net,
    chart_b58_buy_sell, chart_conviction_scores, chart_buy_streak,
    chart_entry_vs_ltp, chart_price_change, chart_rsi_velocity,
    chart_volatility_map, chart_decision_scores, chart_sector_heatmap,
    chart_sector_cumulative,
)


def fig_to_html(fig: go.Figure, div_id: str, height: str = "380px") -> str:
    """Convert a Plotly figure to an inline HTML div."""
    html = pio.to_html(fig, full_html=False, include_plotlyjs=False,
                       div_id=div_id, default_width="100%",
                       default_height=height, config={"displayModeBar": False})
    return html


def df_to_html_table(df: pd.DataFrame, cols: list, headers: list,
                     color_cols: dict = None, max_rows: int = 15) -> str:
    """Convert a DataFrame to a styled HTML table."""
    rows_html = []
    for _, row in df.head(max_rows).iterrows():
        cells = []
        for col in cols:
            val = row[col]
            style = ""
            if color_cols and col in color_cols:
                fn = color_cols[col]
                style = f' style="color:{fn(val)}"'
            cells.append(f"<td{style}>{val}</td>")
        rows_html.append("<tr>" + "".join(cells) + "</tr>")

    header_html = "".join(f"<th>{h}</th>" for h in headers)
    return f"""
    <div class="tbl-wrap">
      <table>
        <thead><tr>{header_html}</tr></thead>
        <tbody>{"".join(rows_html)}</tbody>
      </table>
    </div>"""


def generate_report(data: Dict, output_path: str = "nepse_report.html") -> str:
    """
    Generate the complete HTML report.
    Returns the output path.
    """
    market_df   = data["market"]
    tech_df     = data["technical"]
    b58_df      = data["b58"]
    subindex_df = data["subindex"]
    movers_df   = data["movers"]

    print("Running analyses...")
    regime       = detect_market_regime(market_df)
    conv_df      = compute_b58_conviction(b58_df, market_df)
    scores_df    = compute_decision_scores(tech_df, b58_df, market_df)
    rsi_trends   = get_rsi_trend(tech_df)
    sector_data  = get_sector_momentum(subindex_df)
    correlation  = compute_b58_nepse_correlation(market_df)
    last         = market_df.iloc[-1]
    first        = market_df.iloc[0]
    n_days       = len(market_df)

    print("Generating charts...")

    # ── OVERVIEW CHARTS
    c_nepse    = fig_to_html(chart_nepse_trend(market_df),    "c_nepse")
    c_turnover = fig_to_html(chart_turnover(market_df),       "c_turnover")
    c_b58nepse = fig_to_html(chart_b58_net_vs_nepse(market_df), "c_b58nepse")
    c_advdec   = fig_to_html(chart_advance_decline(market_df),  "c_advdec")

    # ── SIGNAL CHARTS
    c_donut    = fig_to_html(chart_action_donut(tech_df),     "c_donut", "300px")
    c_rdist    = fig_to_html(chart_rsi_distribution(tech_df), "c_rdist", "300px")
    c_matrix   = fig_to_html(chart_rsi_adx_matrix(tech_df),  "c_matrix")
    c_rheat    = fig_to_html(chart_rsi_heatmap(tech_df),      "c_rheat",
                              f"{max(380, len(tech_df['sym'].unique()) * 22 + 80)}px")
    c_rtrend   = fig_to_html(chart_rsi_trend_lines(tech_df),  "c_rtrend")

    # ── B58 CHARTS
    c_bnet     = fig_to_html(chart_b58_daily_net(market_df),    "c_bnet")
    c_mkt      = fig_to_html(chart_b58_market_share(b58_df),    "c_mkt")
    c_cumnet   = fig_to_html(chart_b58_cumulative_net(b58_df),  "c_cumnet")
    c_buysell  = fig_to_html(chart_b58_buy_sell(b58_df),        "c_buysell")

    # ── CONVICTION CHARTS
    c_conv     = fig_to_html(chart_conviction_scores(conv_df),  "c_conv", "420px")
    c_streak   = fig_to_html(chart_buy_streak(conv_df),         "c_streak")
    c_entry    = fig_to_html(chart_entry_vs_ltp(conv_df, tech_df), "c_entry")

    # ── MOMENTUM CHARTS
    c_pchg     = fig_to_html(chart_price_change(tech_df),       "c_pchg")
    c_rvel     = fig_to_html(chart_rsi_velocity(tech_df),       "c_rvel")
    c_vmap     = fig_to_html(chart_volatility_map(tech_df),     "c_vmap")

    # ── DECISION CHART
    c_score    = fig_to_html(chart_decision_scores(scores_df),  "c_score")

    # ── SECTOR CHARTS
    c_sectheat = fig_to_html(chart_sector_heatmap(subindex_df),    "c_sectheat", "420px")
    c_sectcum  = fig_to_html(chart_sector_cumulative(subindex_df), "c_sectcum")

    # ── KPI VALUES
    nepse_delta = last["nepse_close"] - first["nepse_close"]
    buy_days    = market_df["is_b58_buyer"].sum()
    avg_tov     = market_df["turnover_b"].mean()
    total_net   = market_df["b58_net_m"].sum()

    # ── DECISION TABLE
    sig_map = {"STRONG BUY": COLORS["accent"], "BUY/ADD": COLORS["green"],
               "HOLD/WATCH": COLORS["blue"], "WATCH": COLORS["amber"], "AVOID": COLORS["red"]}

    dec_rows = ""
    for _, r in scores_df.head(15).iterrows():
        color = sig_map.get(r["decision"], COLORS["muted"])
        streak_html = "🔥" * min(int(r["buy_streak"]) // 3, 3)
        dec_rows += f"""
        <tr>
          <td><strong>{r['sym']}</strong></td>
          <td>{r['ltp_latest']:,.0f}</td>
          <td class="{'up' if r['rsi_latest']>=55 else 'dn' if r['rsi_latest']<=35 else 'neu'}">{r['rsi_latest']:.1f}</td>
          <td>{r['adx_latest']:.1f}</td>
          <td class="{'up' if r['ad_osc']=='Bullish' else 'dn'}">{r['ad_osc'] or '—'}</td>
          <td class="{'up' if r['buy_streak']>=3 else ''}">{int(r['buy_streak'])}d {streak_html}</td>
          <td class="neu"><strong>{r['total_score']:.0f}</strong></td>
          <td><span class="sig" style="background:{color}20;color:{color};border:1px solid {color}40">{r['decision']}</span></td>
        </tr>"""

    # ── INSIGHT GENERATION
    insights = []
    nd_dir = "up" if nepse_delta >= 0 else "down"
    nd_color = COLORS["green"] if nepse_delta >= 0 else COLORS["red"]
    insights.append((nd_color, "bull" if nepse_delta >= 0 else "bear",
        f"<strong>NEPSE {n_days}-Session Trend:</strong> Index moved from {first['nepse_close']:,.2f} → {last['nepse_close']:,.2f} ({'+' if nepse_delta >= 0 else ''}{nepse_delta:.2f} pts). Market regime: <strong>{regime['regime']}</strong>."))

    b58_rate = regime["b58_buy_rate"]
    insights.append((COLORS["green"] if b58_rate >= 50 else COLORS["red"], "bull" if b58_rate >= 50 else "bear",
        f"<strong>B58 Institutional Bias:</strong> Net buyer in {buy_days}/{n_days} sessions ({b58_rate:.0f}%). Total net flow: ₨{total_net:+.1f}M. {'Accumulation bias — institutional buying dominant.' if b58_rate >= 50 else 'Distribution phase — smart money reducing exposure.'}"))

    high_conv = scores_df[(scores_df["buy_streak"] >= 3) & (scores_df["total_score"] >= 60)]
    if len(high_conv):
        streaks = ", ".join([f"{r['sym']} ({int(r['buy_streak'])}d)" for _, r in high_conv.iterrows()])
        insights.append((COLORS["accent"], "bull",
            f"<strong>High Conviction Accumulation:</strong> {streaks} — Multi-day B58 buy streaks with strong technical scores. Institutional conviction plays."))

    oversold = rsi_trends[rsi_trends["rsi_latest"] < 35]
    if len(oversold):
        syms = ", ".join(oversold["sym"].tolist())
        insights.append((COLORS["amber"], "watch",
            f"<strong>Oversold Watch (RSI&lt;35):</strong> {syms} — Approaching technical bounce territory. Confirm with B58 accumulation before entry."))

    high_vol = tech_df[tech_df["date"] == tech_df["date"].max()]
    high_vol = high_vol[high_vol["atr"] >= 40]
    if len(high_vol):
        syms = ", ".join(high_vol["sym"].tolist())
        insights.append((COLORS["red"], "bear",
            f"<strong>High Volatility Alert (ATR≥40):</strong> {syms} — Reduce position sizing, use tighter stop losses."))

    corr_color = COLORS["green"] if correlation["correlation"] > 0.3 else COLORS["amber"]
    insights.append((corr_color, "info",
        f"<strong>B58 → NEPSE Correlation:</strong> B58 net flow correlates {correlation['correlation']:+.3f} with next-day NEPSE change. Same-direction accuracy: {correlation['same_direction_pct']:.0f}%. {correlation['interpretation']}."))

    insights_html = "\n".join([
        f'<div class="ins {cls}" style="border-left-color:{color}">{text}</div>'
        for color, cls, text in insights
    ])

    print("Assembling HTML report...")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NEPSE B58 Intelligence — Python Analysis Report</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600;700&family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{{
  --bg:#080c10;--bg2:#0d1219;--bg3:#111922;--border:#1e2d3d;
  --text:#cdd9e5;--muted:#576f86;--green:#3fb950;--red:#f85149;
  --amber:#e3b341;--blue:#58a6ff;--accent:#f0b429;
  --mono:'IBM Plex Mono',monospace;--sans:'IBM Plex Sans',sans-serif;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:13px}}
body::before{{content:'';position:fixed;inset:0;background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,0.025) 2px,rgba(0,0,0,0.025) 4px);pointer-events:none;z-index:9999}}
.topbar{{background:var(--bg2);border-bottom:1px solid var(--border);padding:0 24px;height:56px;display:flex;align-items:center;gap:16px;position:sticky;top:0;z-index:100}}
.logo{{font-family:var(--mono);font-size:15px;font-weight:700;color:var(--accent);letter-spacing:2px}}
.logo span{{color:var(--muted);font-weight:300}}
.tag{{font-family:var(--mono);font-size:10px;background:var(--bg3);border:1px solid var(--border);padding:3px 10px;border-radius:3px;color:var(--muted)}}
.tag.py{{border-color:rgba(88,166,255,.4);color:var(--blue)}}
.ml{{margin-left:auto}}
.dot{{width:7px;height:7px;border-radius:50%;background:var(--green)}}
.tabs{{background:var(--bg2);border-bottom:1px solid var(--border);display:flex;padding:0 24px;overflow-x:auto}}
.tab{{font-family:var(--mono);font-size:10px;padding:13px 16px;cursor:pointer;color:var(--muted);border-bottom:2px solid transparent;white-space:nowrap;letter-spacing:.8px;transition:.15s all}}
.tab:hover{{color:var(--text)}}.tab.active{{color:var(--accent);border-bottom-color:var(--accent)}}
.tab .n{{color:var(--border);font-size:9px;margin-right:5px}}
.content{{padding:22px 24px}}
.panel{{display:none}}.panel.active{{display:block}}
.g2{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px}}
.g3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;margin-bottom:14px}}
.g4{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:14px}}
.g5{{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:14px}}
@media(max-width:900px){{.g2,.g3,.g4,.g5{{grid-template-columns:1fr}}}}
.kpi{{background:var(--bg2);border:1px solid var(--border);border-radius:6px;padding:14px 16px;position:relative;overflow:hidden}}
.kpi::before{{content:'';position:absolute;top:0;left:0;right:0;height:2px}}
.kpi.g::before{{background:var(--green)}}.kpi.r::before{{background:var(--red)}}
.kpi.a::before{{background:var(--amber)}}.kpi.b::before{{background:var(--blue)}}
.kpi-l{{font-family:var(--mono);font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:1.5px;margin-bottom:6px}}
.kpi-v{{font-family:var(--mono);font-size:21px;font-weight:700;line-height:1}}
.kpi-s{{font-family:var(--mono);font-size:9px;color:var(--muted);margin-top:5px}}
.card{{background:var(--bg2);border:1px solid var(--border);border-radius:6px;padding:16px;margin-bottom:14px}}
.card.nm{{margin-bottom:0}}
.ch{{font-family:var(--mono);font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:12px}}
.up{{color:var(--green)!important}}.dn{{color:var(--red)!important}}.neu{{color:var(--amber)!important}}
.tbl-wrap{{overflow:auto;max-height:360px}}
.tbl-wrap::-webkit-scrollbar{{width:3px;height:3px}}
.tbl-wrap::-webkit-scrollbar-thumb{{background:var(--border)}}
table{{width:100%;border-collapse:collapse;font-size:11px;font-family:var(--mono)}}
th{{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.8px;padding:6px 10px;border-bottom:1px solid var(--border);text-align:left;position:sticky;top:0;background:var(--bg2)}}
td{{padding:6px 10px;border-bottom:1px solid var(--bg3)}}
tr:hover td{{background:var(--bg3)}}
td strong{{color:var(--text)}}
.sig{{display:inline-block;padding:2px 8px;border-radius:3px;font-size:9px;font-weight:700;font-family:var(--mono)}}
.regime-box{{background:linear-gradient(135deg,var(--bg2),var(--bg3));border-radius:6px;padding:20px 24px;margin-bottom:14px;border:1px solid var(--border)}}
.regime-label{{font-family:var(--mono);font-size:18px;font-weight:700;margin-bottom:8px}}
.regime-stats{{display:flex;gap:24px;flex-wrap:wrap;font-family:var(--mono);font-size:11px;color:var(--muted)}}
.regime-stat strong{{color:var(--text)}}
.ins{{border-left:3px solid var(--border);padding:10px 14px;background:var(--bg3);border-radius:0 5px 5px 0;font-size:12px;line-height:1.6;margin-bottom:8px}}
.ins strong{{color:var(--text);font-family:var(--mono);font-size:11px}}
.section-label{{font-family:var(--mono);font-size:10px;color:var(--accent);text-transform:uppercase;letter-spacing:2px;margin-bottom:14px;padding-bottom:8px;border-bottom:1px solid var(--border)}}
.section-label::before{{content:'// ';color:var(--border)}}
.footer{{text-align:center;font-family:var(--mono);font-size:10px;color:var(--muted);padding:24px;border-top:1px solid var(--border);margin-top:24px}}
.footer a{{color:var(--blue);text-decoration:none}}
</style>
</head>
<body>

<div class="topbar">
  <div class="logo">B58<span>/</span>INTEL</div>
  <div class="tag py">Python + Pandas + Plotly</div>
  <div class="tag">{n_days} Sessions Loaded</div>
  <div class="tag">{market_df['date'].iloc[0].strftime('%b %d')} → {market_df['date'].iloc[-1].strftime('%b %d, %Y')}</div>
  <div class="ml" style="display:flex;align-items:center;gap:10px">
    <div class="dot"></div>
    <div style="font-family:var(--mono);font-size:10px;color:var(--muted)">NEPSE {last['nepse_close']:,.2f} <span class="{'up' if last['nepse_chg_pct']>=0 else 'dn'}">{last['nepse_chg_pct']:+.2f}%</span></div>
    <div style="font-family:var(--mono);font-size:10px;color:var(--muted)">B58 <span class="{'up' if last['b58_net_m']>=0 else 'dn'}">₨{last['b58_net_m']:+.1f}M</span></div>
  </div>
</div>

<div class="tabs">
  <div class="tab active" onclick="ST('overview',this)"><span class="n">01</span>OVERVIEW</div>
  <div class="tab" onclick="ST('signals',this)"><span class="n">02</span>SIGNALS</div>
  <div class="tab" onclick="ST('b58flow',this)"><span class="n">03</span>B58 FLOW</div>
  <div class="tab" onclick="ST('heatmap',this)"><span class="n">04</span>RSI MAP</div>
  <div class="tab" onclick="ST('momentum',this)"><span class="n">05</span>MOMENTUM</div>
  <div class="tab" onclick="ST('conviction',this)"><span class="n">06</span>CONVICTION</div>
  <div class="tab" onclick="ST('decision',this)"><span class="n">07</span>DECISION ENGINE</div>
  <div class="tab" onclick="ST('sectors',this)"><span class="n">08</span>SECTORS</div>
</div>

<div class="content">

<!-- 01 OVERVIEW -->
<div class="panel active" id="tab-overview">
  <div class="regime-box" style="border-color:{regime['color']}40">
    <div class="regime-label" style="color:{regime['color']}">{regime['regime']}</div>
    <div class="regime-stats">
      <span>NEPSE 5D: <strong class="{'up' if regime['nepse_5d_chg']>=0 else 'dn'}">{regime['nepse_5d_chg']:+.2f}%</strong></span>
      <span>B58 Buy Rate: <strong>{regime['b58_buy_rate']:.0f}%</strong></span>
      <span>Avg A/D: <strong>{regime['avg_adv_dec_pct']:.0f}%</strong></span>
      <span>Avg Turnover: <strong>₨{regime['avg_turnover_b']:.2f}B</strong></span>
      <span>5D B58 Net: <strong class="{'up' if regime['total_b58_net_m']>=0 else 'dn'}">₨{regime['total_b58_net_m']:+.1f}M</strong></span>
      <span>Corr(B58→NEPSE): <strong>{correlation['correlation']:+.3f}</strong></span>
    </div>
  </div>
  <div class="g5" style="margin-bottom:14px">
    <div class="kpi {'g' if nepse_delta>=0 else 'r'}">
      <div class="kpi-l">NEPSE Δ ({n_days}D)</div>
      <div class="kpi-v {'up' if nepse_delta>=0 else 'dn'}">{nepse_delta:+.0f}</div>
      <div class="kpi-s">{first['nepse_close']:,.2f} → {last['nepse_close']:,.2f}</div>
    </div>
    <div class="kpi a">
      <div class="kpi-l">Latest Close</div>
      <div class="kpi-v neu">{last['nepse_close']:,.2f}</div>
      <div class="kpi-s">{last['nepse_chg_pct']:+.2f}%</div>
    </div>
    <div class="kpi {'g' if buy_days>n_days/2 else 'r'}">
      <div class="kpi-l">B58 Buy Days</div>
      <div class="kpi-v {'up' if buy_days>n_days/2 else 'dn'}">{int(buy_days)}/{n_days}</div>
      <div class="kpi-s">{buy_days/n_days*100:.0f}% bullish sessions</div>
    </div>
    <div class="kpi b">
      <div class="kpi-l">Avg Turnover</div>
      <div class="kpi-v" style="color:var(--blue)">₨{avg_tov:.2f}B</div>
      <div class="kpi-s">Daily average</div>
    </div>
    <div class="kpi {'g' if total_net>=0 else 'r'}">
      <div class="kpi-l">Total B58 Net</div>
      <div class="kpi-v {'up' if total_net>=0 else 'dn'}">₨{total_net:+.1f}M</div>
      <div class="kpi-s">Cumulative flow</div>
    </div>
  </div>
  <div class="g2">{c_nepse}{c_turnover}</div>
  <div class="g2">{c_b58nepse}{c_advdec}</div>
</div>

<!-- 02 SIGNALS -->
<div class="panel" id="tab-signals">
  <div class="g3" style="margin-bottom:14px">
    <div class="card nm"><div class="ch">Action Distribution — Latest Session</div>{c_donut}</div>
    <div class="card nm"><div class="ch">RSI Distribution by Signal</div>{c_rdist}</div>
    <div class="card nm"><div class="ch">Signal Summary</div>
      {df_to_html_table(
        tech_df[tech_df["date"]==tech_df["date"].max()].sort_values("rsi", ascending=False),
        ["sym","ltp","rsi","adx","atr","ad_osc","action"],
        ["Symbol","LTP","RSI","ADX","ATR","AD Osc","Action"]
      )}
    </div>
  </div>
  <div class="g2">
    <div class="card nm"><div class="ch">RSI × ADX Momentum Matrix</div>{c_matrix}</div>
    <div class="card nm"><div class="ch">RSI Trend — Top Symbols</div>{c_rtrend}</div>
  </div>
</div>

<!-- 03 B58 FLOW -->
<div class="panel" id="tab-b58flow">
  <div class="g4" style="margin-bottom:14px">
    <div class="kpi g">
      <div class="kpi-l">Total Purchases</div>
      <div class="kpi-v up">₨{market_df['b58_purchase_m'].sum():.0f}M</div>
      <div class="kpi-s">{n_days} sessions</div>
    </div>
    <div class="kpi r">
      <div class="kpi-l">Total Sales</div>
      <div class="kpi-v dn">₨{market_df['b58_sale_m'].sum():.0f}M</div>
      <div class="kpi-s">{n_days} sessions</div>
    </div>
    <div class="kpi {'g' if total_net>=0 else 'r'}">
      <div class="kpi-l">Net Flow</div>
      <div class="kpi-v {'up' if total_net>=0 else 'dn'}">₨{total_net:+.1f}M</div>
      <div class="kpi-s">Net {'BUY' if total_net>=0 else 'SELL'}</div>
    </div>
    <div class="kpi b">
      <div class="kpi-l">Buy Sessions / Total</div>
      <div class="kpi-v" style="color:var(--blue)">{int(buy_days)}/{n_days}</div>
      <div class="kpi-s">{buy_days/n_days*100:.0f}% bullish</div>
    </div>
  </div>
  <div class="g2">{c_bnet}{c_mkt}</div>
  <div class="g2">{c_cumnet}{c_buysell}</div>
</div>

<!-- 04 RSI HEATMAP -->
<div class="panel" id="tab-heatmap">
  <div class="card nm" style="margin-bottom:14px">
    <div class="ch">RSI Heatmap — All Symbols × All Sessions</div>
    {c_rheat}
  </div>
</div>

<!-- 05 MOMENTUM -->
<div class="panel" id="tab-momentum">
  <div class="g2">{c_pchg}{c_rvel}</div>
  <div class="g2">{c_vmap}
    <div class="card nm">
      <div class="ch">ATR Volatility Map</div>
      {df_to_html_table(
        tech_df[tech_df["date"]==tech_df["date"].max()].sort_values("atr", ascending=False),
        ["sym","ltp","atr","rsi","adx","action"],
        ["Symbol","LTP","ATR","RSI","ADX","Action"]
      )}
    </div>
  </div>
</div>

<!-- 06 CONVICTION -->
<div class="panel" id="tab-conviction">
  <div class="g2">
    <div class="card nm"><div class="ch">Conviction Score Ranking</div>{c_conv}</div>
    <div class="card nm"><div class="ch">Consecutive Buy Streak</div>{c_streak}
      <div style="height:14px"></div>
      <div class="ch">Avg Entry vs Current LTP</div>{c_entry}
    </div>
  </div>
</div>

<!-- 07 DECISION ENGINE -->
<div class="panel" id="tab-decision">
  <div class="g2">
    <div class="card nm">
      <div class="ch">Multi-Factor Score</div>
      {c_score}
    </div>
    <div class="card nm">
      <div class="ch">AI Insights & Observations</div>
      {insights_html}
    </div>
  </div>
  <div class="card" style="margin-top:14px">
    <div class="ch">Decision Engine — Full Ranking Table</div>
    <div class="tbl-wrap">
      <table>
        <thead><tr><th>Symbol</th><th>LTP</th><th>RSI</th><th>ADX</th><th>AD Osc</th><th>Streak</th><th>Score</th><th>Decision</th></tr></thead>
        <tbody>{dec_rows}</tbody>
      </table>
    </div>
  </div>
</div>

<!-- 08 SECTORS -->
<div class="panel" id="tab-sectors">
  <div class="card nm" style="margin-bottom:14px">
    <div class="ch">Sector Performance Heatmap</div>
    {c_sectheat}
  </div>
  <div class="g2">
    <div class="card nm"><div class="ch">Cumulative Sector Performance</div>{c_sectcum}</div>
    <div class="card nm">
      <div class="ch">Sector Win Rate & Avg Daily Change</div>
      {df_to_html_table(
        sector_data["summary"],
        ["name","win_rate_pct","avg_daily_chg"],
        ["Sector","Win Rate %","Avg Daily Chg %"]
      )}
    </div>
  </div>
</div>

</div><!-- /content -->

<div class="footer">
  NEPSE B58 Intelligence Dashboard — Generated by Python + Pandas + Plotly<br>
  Broker 58 (Naasa Securities) · Data: {market_df['date'].iloc[0].strftime('%Y-%m-%d')} to {market_df['date'].iloc[-1].strftime('%Y-%m-%d')}<br>
  Prepared by Sagun Prajapati, MBA (Finance) ·
  <a href="https://sagunprajapati.github.io/share/" target="_blank">Main Report</a> ·
  For personal tracking only. Not financial advice.
</div>

<script>
function ST(id,el){{
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.getElementById('tab-'+id).classList.add('active');
  el.classList.add('active');
  // Trigger Plotly resize
  setTimeout(()=>window.dispatchEvent(new Event('resize')),100);
}}
</script>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n✅ Report saved to: {output_path}")
    print(f"   File size: {len(html)/1024:.1f} KB")
    return output_path
