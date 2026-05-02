"""
NEPSE B58 Analysis — Configuration
===================================
Broker 58 (Naasa Securities) Daily Intelligence Suite
Prepared by Sagun Prajapati, MBA (Finance)
"""

GITHUB_BASE = "https://raw.githubusercontent.com/SagunPrajapati/share/main/"

DATES = [
    "2026-04-13", "2026-04-15", "2026-04-16", "2026-04-17",
    "2026-04-20", "2026-04-21", "2026-04-22", "2026-04-23",
    "2026-04-24", "2026-04-27", "2026-04-28", "2026-04-29",
    "2026-04-30",
]

COLORS = {
    "bg": "#080c10", "bg2": "#0d1219", "bg3": "#111922",
    "border": "#1e2d3d", "text": "#cdd9e5", "muted": "#576f86",
    "green": "#3fb950", "red": "#f85149", "amber": "#e3b341",
    "blue": "#58a6ff", "purple": "#bc8cff", "accent": "#f0b429",
}

PLOTLY_LAYOUT = dict(
    paper_bgcolor=COLORS["bg2"], plot_bgcolor=COLORS["bg3"],
    font=dict(color=COLORS["muted"], family="'IBM Plex Mono', monospace", size=11),
    xaxis=dict(gridcolor=COLORS["bg3"], linecolor=COLORS["border"], tickfont=dict(size=10)),
    yaxis=dict(gridcolor=COLORS["bg3"], linecolor=COLORS["border"], tickfont=dict(size=10)),
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=10)),
    margin=dict(t=40, r=20, b=40, l=60),
    colorway=["#f0b429","#3fb950","#58a6ff","#f85149","#bc8cff","#39d353","#e3b341"],
)

ACTION_COLORS = {
    "BUY": "#3fb950", "ADD": "#3fb950", "BUY/ADD": "#3fb950",
    "HOLD": "#58a6ff", "WATCH": "#e3b341", "AVOID": "#f85149",
}

SECTOR_COLORS = {
    "Banking SubIndex": "#58a6ff", "Development Bank Index": "#79c0ff",
    "Finance Index": "#bc8cff", "Hotels And Tourism Index": "#f0b429",
    "HydroPower Index": "#39d353", "Investment Index": "#e3b341",
    "Life Insurance": "#f85149", "Manufacturing And Processing": "#3fb950",
    "Microfinance Index": "#d29922", "Mutual Fund": "#576f86",
    "Non Life Insurance": "#ffa657", "Others Index": "#8b949e",
    "Trading Index": "#cdd9e5",
}
