"""
NEPSE B58 Analysis — Analysis Engine
======================================
All analytical computations:
  - RSI / ADX / ATR trend analysis
  - B58 conviction scoring
  - Multi-factor decision engine
  - Sector rotation detection
  - Momentum & volatility ranking
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple


# ── TECHNICAL ANALYSIS ───────────────────────────────────────────────────────

def rsi_zone(rsi: float) -> str:
    """Classify RSI into zone."""
    if rsi < 30:   return "OVERSOLD"
    elif rsi < 35: return "NEAR OVERSOLD"
    elif rsi < 45: return "WEAK"
    elif rsi < 55: return "NEUTRAL"
    elif rsi < 65: return "STRONG"
    else:          return "OVERBOUGHT"


def adx_strength(adx: float) -> str:
    """Classify ADX trend strength."""
    if adx < 15:   return "NO TREND"
    elif adx < 20: return "WEAK TREND"
    elif adx < 25: return "MODERATE"
    elif adx < 30: return "STRONG"
    else:          return "VERY STRONG"


def get_rsi_trend(tech_df: pd.DataFrame) -> pd.DataFrame:
    """
    For each symbol: compute RSI velocity (day-over-day change),
    7-day RSI range, and trend direction.
    """
    rows = []
    for sym, grp in tech_df.groupby("sym"):
        grp = grp.sort_values("date")
        rsis = grp["rsi"].values
        if len(rsis) >= 2:
            velocity = rsis[-1] - rsis[-2]
            rsi_5d   = np.mean(rsis[-5:]) if len(rsis) >= 5 else np.mean(rsis)
            rsi_min  = rsis.min()
            rsi_max  = rsis.max()
        else:
            velocity = 0; rsi_5d = rsis[-1] if len(rsis) else 0
            rsi_min = rsi_max = rsi_5d

        latest = grp.iloc[-1]
        rows.append({
            "sym":         sym,
            "rsi_latest":  latest["rsi"],
            "rsi_prev":    rsis[-2] if len(rsis) >= 2 else latest["rsi"],
            "rsi_velocity": velocity,
            "rsi_5d_avg":  rsi_5d,
            "rsi_min":     rsi_min,
            "rsi_max":     rsi_max,
            "adx_latest":  latest["adx"],
            "atr_latest":  latest["atr"],
            "ltp_latest":  latest["ltp"],
            "ad_osc":      latest["ad_osc"],
            "action":      latest["action"],
            "zone":        rsi_zone(latest["rsi"]),
            "trend_str":   adx_strength(latest["adx"]),
            "sessions":    len(grp),
        })
    return pd.DataFrame(rows).sort_values("rsi_latest", ascending=False).reset_index(drop=True)


def get_price_momentum(tech_df: pd.DataFrame) -> pd.DataFrame:
    """Compute price % change from first to last available session per symbol."""
    rows = []
    for sym, grp in tech_df.groupby("sym"):
        grp = grp.sort_values("date")
        if len(grp) >= 2:
            first_ltp = grp.iloc[0]["ltp"]
            last_ltp  = grp.iloc[-1]["ltp"]
            if first_ltp > 0:
                pct = (last_ltp - first_ltp) / first_ltp * 100
            else:
                pct = 0.0
        else:
            pct = grp.iloc[-1]["chg_pct"] if len(grp) else 0.0
        rows.append({
            "sym":       sym,
            "first_ltp": grp.iloc[0]["ltp"],
            "last_ltp":  grp.iloc[-1]["ltp"],
            "chg_pct":   round(pct, 2),
            "sessions":  len(grp),
            "action":    grp.iloc[-1]["action"],
        })
    return pd.DataFrame(rows).sort_values("chg_pct", ascending=False).reset_index(drop=True)


# ── B58 CONVICTION ENGINE ─────────────────────────────────────────────────────

def compute_b58_conviction(b58_df: pd.DataFrame, market_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute B58 conviction score per symbol.

    Score components (100 total):
      - Net kitta accumulated (0-30): scale by total market
      - Buy days count       (0-20): more buy sessions = higher conviction
      - Avg market share %   (0-20): dominant buyer = high conviction
      - Consecutive streak   (0-20): recent activity more valuable
      - Net vs gross ratio   (0-10): pure buyer vs two-way trader

    Returns DataFrame sorted by conviction score descending.
    """
    # Get all dates sorted
    all_dates = sorted(market_df["date"].unique())

    agg = b58_df.groupby("sym").agg(
        total_buy_kitta  = ("buy_kitta",     "sum"),
        total_sell_kitta = ("sell_kitta",    "sum"),
        total_buy_amt_m  = ("buy_amount_m",  "sum"),
        total_sell_amt_m = ("sell_amount_m", "sum"),
        buy_days         = ("buy_kitta",     lambda x: (x > 0).sum()),
        sell_days        = ("sell_kitta",    lambda x: (x > 0).sum()),
        avg_buy_mkt_pct  = ("buy_mkt_pct",  lambda x: x[x > 0].mean() if (x > 0).any() else 0),
        avg_buy_price    = ("buy_avg_price", lambda x: x[x > 0].mean() if (x > 0).any() else 0),
        sessions_appeared= ("date",         "count"),
    ).reset_index()

    agg["net_kitta"]    = agg["total_buy_kitta"] - agg["total_sell_kitta"]
    agg["net_amount_m"] = agg["total_buy_amt_m"] - agg["total_sell_amt_m"]

    # Compute consecutive buy streak (from latest date backwards)
    streak_map = {}
    for sym, grp in b58_df.groupby("sym"):
        grp = grp.sort_values("date")
        streak = 0
        for _, row in grp.sort_values("date", ascending=False).iterrows():
            if row["buy_kitta"] > 0:
                streak += 1
            else:
                break
        streak_map[sym] = streak
    agg["buy_streak"] = agg["sym"].map(streak_map).fillna(0).astype(int)

    # Normalize and score
    max_net     = agg["net_kitta"].abs().max() or 1
    max_days    = agg["buy_days"].max() or 1
    max_mkt     = agg["avg_buy_mkt_pct"].max() or 1
    max_streak  = agg["buy_streak"].max() or 1

    agg["score_net"]    = (agg["net_kitta"].clip(lower=0) / max_net * 30).round(1)
    agg["score_days"]   = (agg["buy_days"] / max_days * 20).round(1)
    agg["score_mkt"]    = (agg["avg_buy_mkt_pct"] / max_mkt * 20).round(1)
    agg["score_streak"] = (agg["buy_streak"] / max_streak * 20).round(1)

    # Net ratio: pure buyer = 10, heavy seller = 0
    total_activity = agg["total_buy_kitta"] + agg["total_sell_kitta"]
    agg["net_ratio"] = np.where(
        total_activity > 0,
        agg["total_buy_kitta"] / total_activity,
        0.5
    )
    agg["score_ratio"] = (agg["net_ratio"] * 10).round(1)

    agg["conviction_score"] = (
        agg["score_net"] + agg["score_days"] +
        agg["score_mkt"] + agg["score_streak"] + agg["score_ratio"]
    ).round(1)

    agg["conviction_label"] = pd.cut(
        agg["conviction_score"],
        bins=[0, 20, 40, 60, 80, 100],
        labels=["WEAK", "MODERATE", "STRONG", "VERY STRONG", "EXTREME"]
    )

    return agg.sort_values("conviction_score", ascending=False).reset_index(drop=True)


# ── DECISION ENGINE ───────────────────────────────────────────────────────────

def compute_decision_scores(
    tech_df: pd.DataFrame,
    b58_df: pd.DataFrame,
    market_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Multi-factor decision scoring system.

    Factors:
      RSI position    (0-25): sweet spot 40-60 scores highest
      ADX strength    (0-20): trending markets score higher
      B58 conviction  (0-30): institutional backing
      AD Oscillator   (0-15): accumulation vs distribution
      RSI velocity    (0-10): improving momentum bonus
    """
    rsi_trends = get_rsi_trend(tech_df)
    b58_scores = compute_b58_conviction(b58_df, market_df)

    # Merge
    df = rsi_trends.merge(
        b58_scores[["sym", "conviction_score", "buy_streak", "net_kitta",
                    "total_buy_kitta", "total_sell_kitta", "avg_buy_mkt_pct"]],
        on="sym", how="left"
    )
    df["conviction_score"] = df["conviction_score"].fillna(0)
    df["buy_streak"]       = df["buy_streak"].fillna(0).astype(int)

    # RSI Score: peak 40-62 (momentum building)
    def rsi_score(rsi):
        if 40 <= rsi <= 62: return 25
        elif 35 <= rsi < 40: return 18
        elif 62 < rsi <= 70: return 15
        elif rsi < 35: return 5
        else: return 10  # > 70 overbought
    df["score_rsi"] = df["rsi_latest"].apply(rsi_score)

    # ADX Score: stronger trend = higher score
    def adx_score(adx):
        if adx >= 25: return 20
        elif adx >= 20: return 15
        elif adx >= 15: return 10
        else: return 5
    df["score_adx"] = df["adx_latest"].apply(adx_score)

    # B58 Score: normalized conviction (0-30)
    max_conv = df["conviction_score"].max() or 1
    df["score_b58"] = (df["conviction_score"] / max_conv * 30).round(1)

    # AD Oscillator Score
    df["score_ad"] = df["ad_osc"].map({"Bullish": 15, "Bearish": 3}).fillna(8)

    # RSI Velocity Score: positive momentum bonus
    df["score_velocity"] = df["rsi_velocity"].apply(
        lambda v: min(10, max(0, v * 2))
    ).round(1)

    # Total Score
    df["total_score"] = (
        df["score_rsi"] + df["score_adx"] + df["score_b58"] +
        df["score_ad"] + df["score_velocity"]
    ).round(1)

    # Decision
    def decision(score):
        if score >= 75: return "STRONG BUY"
        elif score >= 60: return "BUY/ADD"
        elif score >= 45: return "HOLD/WATCH"
        elif score >= 30: return "WATCH"
        else: return "AVOID"
    df["decision"] = df["total_score"].apply(decision)

    # Risk flag
    df["high_risk"] = df["atr_latest"] >= 40
    df["oversold"]  = df["rsi_latest"] < 35
    df["overbought"] = df["rsi_latest"] > 65

    return df.sort_values("total_score", ascending=False).reset_index(drop=True)


# ── SECTOR ANALYSIS ───────────────────────────────────────────────────────────

def get_sector_momentum(subindex_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute sector performance metrics.
    Returns pivoted DataFrame with sector × date values.
    """
    pivot = subindex_df.pivot_table(
        index="date", columns="name", values="chg_pct", aggfunc="first"
    ).fillna(0)

    # Cumulative performance
    cum = pivot.cumsum()

    # Latest day performance
    latest = subindex_df[subindex_df["date"] == subindex_df["date"].max()].copy()
    latest = latest.sort_values("chg_pct", ascending=False)

    # Win rate per sector
    win_rate = (subindex_df.groupby("name")["direction"]
                .apply(lambda x: (x == "up").sum() / len(x) * 100)
                .reset_index()
                .rename(columns={"direction": "win_rate_pct"}))

    avg_chg = (subindex_df.groupby("name")["chg_pct"]
               .mean()
               .reset_index()
               .rename(columns={"chg_pct": "avg_daily_chg"}))

    sector_summary = win_rate.merge(avg_chg, on="name")
    sector_summary = sector_summary.sort_values("win_rate_pct", ascending=False)

    return {
        "pivot":   pivot,
        "cum":     cum,
        "latest":  latest,
        "summary": sector_summary,
    }


# ── MARKET REGIME DETECTOR ────────────────────────────────────────────────────

def detect_market_regime(market_df: pd.DataFrame) -> Dict:
    """
    Detect current market regime based on recent data.
    Returns dict with regime label, strength, and key metrics.
    """
    recent = market_df.tail(5)
    last   = market_df.iloc[-1]

    nepse_5d_chg = (
        (recent["nepse_close"].iloc[-1] - recent["nepse_close"].iloc[0]) /
        recent["nepse_close"].iloc[0] * 100
    )
    b58_buy_rate    = recent["is_b58_buyer"].mean() * 100
    avg_adv_dec     = recent["adv_dec_ratio"].mean()
    avg_tov         = recent["turnover_b"].mean()
    total_b58_net   = recent["b58_net_m"].sum()

    # Regime classification
    if nepse_5d_chg > 1 and b58_buy_rate >= 60:
        regime = "BULL RUN"
        color  = "#3fb950"
    elif nepse_5d_chg > 0 and b58_buy_rate >= 40:
        regime = "BULLISH BIAS"
        color  = "#58a6ff"
    elif nepse_5d_chg < -1 and b58_buy_rate < 40:
        regime = "BEARISH BIAS"
        color  = "#f85149"
    elif nepse_5d_chg < -2 and b58_buy_rate < 20:
        regime = "DISTRIBUTION"
        color  = "#f85149"
    else:
        regime = "CONSOLIDATION"
        color  = "#e3b341"

    return {
        "regime":         regime,
        "color":          color,
        "nepse_5d_chg":   round(nepse_5d_chg, 2),
        "b58_buy_rate":   round(b58_buy_rate, 1),
        "avg_adv_dec_pct": round(avg_adv_dec * 100, 1),
        "avg_turnover_b": round(avg_tov, 2),
        "total_b58_net_m": round(total_b58_net, 1),
        "latest_close":   last["nepse_close"],
        "latest_chg":     last["nepse_chg_pct"],
        "b58_stance":     last["b58_stance"],
        "b58_net_m":      last["b58_net_m"],
    }


# ── CORRELATION ANALYSIS ──────────────────────────────────────────────────────

def compute_b58_nepse_correlation(market_df: pd.DataFrame) -> Dict:
    """Compute correlation between B58 net flow and next-day NEPSE change."""
    df = market_df.copy()
    df["next_day_chg"] = df["nepse_chg_pct"].shift(-1)
    df = df.dropna(subset=["next_day_chg", "b58_net_m"])

    corr = df["b58_net_m"].corr(df["next_day_chg"])
    same_direction = (
        ((df["b58_net_m"] > 0) & (df["next_day_chg"] > 0)) |
        ((df["b58_net_m"] < 0) & (df["next_day_chg"] < 0))
    ).mean() * 100

    return {
        "correlation": round(corr, 3),
        "same_direction_pct": round(same_direction, 1),
        "interpretation": (
            "Strong leading indicator" if abs(corr) > 0.5
            else "Moderate indicator" if abs(corr) > 0.3
            else "Weak indicator"
        )
    }
