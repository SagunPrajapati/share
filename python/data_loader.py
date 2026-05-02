"""
NEPSE B58 Analysis — Data Loader
==================================
Fetches all daily JSON reports from GitHub and returns
clean pandas DataFrames ready for analysis.
"""

import requests
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from config import GITHUB_BASE, DATES


# ── RAW JSON LOADER ──────────────────────────────────────────────────────────

def fetch_all_reports(dates: List[str] = DATES) -> List[Dict]:
    """Fetch all JSON reports from GitHub. Returns list of raw dicts."""
    reports = []
    print(f"Fetching {len(dates)} reports from GitHub...")
    for date in dates:
        url = f"{GITHUB_BASE}{date}.json"
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                data["_date"] = date
                reports.append(data)
                print(f"  ✓ {date}")
            else:
                print(f"  ✗ {date} (HTTP {r.status_code})")
        except Exception as e:
            print(f"  ✗ {date} ({e})")
    print(f"\nLoaded {len(reports)}/{len(dates)} reports successfully.\n")
    return reports


# ── DATAFRAME BUILDERS ───────────────────────────────────────────────────────

def build_market_df(reports: List[Dict]) -> pd.DataFrame:
    """
    Build daily market overview DataFrame.
    Columns: date, nepse_close, nepse_chg_pct, turnover_b, transactions,
             shares_traded, advance, decline, unchanged, market_cap,
             b58_net_m, b58_stance, b58_purchase_m, b58_sale_m
    """
    rows = []
    for r in reports:
        chg_raw = r.get("nepseChg", "0")
        chg_pct = 0.0
        try:
            # Extract percentage e.g. "-5.73 (-0.20%)" → -0.20
            import re
            m = re.search(r'\(([-+]?\d+\.?\d*)%\)', chg_raw)
            if m:
                chg_pct = float(m.group(1))
        except Exception:
            pass

        adv_dec = r.get("advDecUnch", "0/0/0").split("/")
        adv  = int(adv_dec[0].strip()) if len(adv_dec) > 0 else 0
        dec  = int(adv_dec[1].strip()) if len(adv_dec) > 1 else 0
        unch = int(adv_dec[2].strip()) if len(adv_dec) > 2 else 0

        # Parse turnover like "Rs.4.92B" → 4.92
        tov_raw = r.get("turnover", "0")
        import re as _re
        _m = _re.search(r"(\d+(?:\.\d+)?)", tov_raw)
        tov = float(_m.group(1)) if _m else 0.0

        # Parse B58 net like "+Rs.161.1M" → 161.1
        net_raw = r.get("b58Net", "0")
        neg = "-" in net_raw
        _nm = _re.search(r"(\d+(?:\.\d+)?)", net_raw)
        net_val = float(_nm.group(1)) if _nm else 0.0
        if neg:
            net_val = -net_val

        # Parse purchases/sales like "Rs.457,499,410" → 457.5M
        pur_raw = str(r.get("b58Purchase", "0")).replace(",", "")
        sal_raw = str(r.get("b58SalesTotal", "0")).replace(",", "")
        _pm = _re.search(r"(\d+(?:\.\d+)?)", pur_raw)
        _sm = _re.search(r"(\d+(?:\.\d+)?)", sal_raw)
        pur = float(_pm.group(1)) / 1e6 if _pm else 0.0
        sal = float(_sm.group(1)) / 1e6 if _sm else 0.0

        rows.append({
            "date":          pd.to_datetime(r["_date"]),
            "nepse_close":   float(r.get("nepseClose", 0)),
            "nepse_chg_pct": chg_pct,
            "turnover_b":    tov,
            "transactions":  int(r.get("transactions", "0").replace(",", "")),
            "shares_traded": int(r.get("sharesTraded", "0").replace(",", "")),
            "advance":       adv,
            "decline":       dec,
            "unchanged":     unch,
            "b58_net_m":     net_val,
            "b58_stance":    r.get("b58Stance", ""),
            "b58_purchase_m": pur,
            "b58_sale_m":    sal,
            "headline":      r.get("headline", ""),
        })

    df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    df["is_b58_buyer"] = df["b58_stance"].str.contains("BUYER", na=False)
    df["adv_dec_ratio"] = df["advance"] / (df["advance"] + df["decline"]).replace(0, np.nan)
    df["cumulative_b58_net"] = df["b58_net_m"].cumsum()
    return df


def build_technical_df(reports: List[Dict]) -> pd.DataFrame:
    """
    Build technical indicators DataFrame.
    One row per symbol per date.
    Columns: date, sym, ltp, w52h, w52l, chg_pct, rsi, adx, atr,
             aroon, ad_osc, signal, action
    """
    rows = []
    for r in reports:
        date = pd.to_datetime(r["_date"])
        for t in r.get("technical", []):
            rows.append({
                "date":    date,
                "sym":     t.get("sym", ""),
                "ltp":     float(str(t.get("ltp", "0")).replace(",", "") or 0),
                "w52h":    float(str(t.get("w52h", "0")).replace(",", "") or 0),
                "w52l":    float(str(t.get("w52l", "0")).replace(",", "") or 0),
                "chg_pct": float(str(t.get("chg", "0")).replace("%", "").replace("+", "") or 0),
                "rsi":     float(t.get("rsi", 0) or 0),
                "adx":     float(t.get("adx", 0) or 0),
                "atr":     float(t.get("atr", 0) or 0),
                "aroon":   float(str(t.get("aroon", "0")).replace("%", "") or 0),
                "ad_osc":  t.get("adOsc", ""),
                "signal":  t.get("signal", ""),
                "action":  t.get("action", ""),
            })
    df = pd.DataFrame(rows).sort_values(["sym", "date"]).reset_index(drop=True)
    # Normalize action
    df["action_grp"] = df["action"].map(
        lambda x: "BUY/ADD" if x in ("BUY", "ADD", "BUY/ADD") else x
    )
    return df


def build_b58_df(reports: List[Dict]) -> pd.DataFrame:
    """
    Build B58 buy/sell activity DataFrame.
    One row per symbol per date (combined buy + sell side).
    """
    rows = []
    for r in reports:
        date = pd.to_datetime(r["_date"])
        buy_map = {}
        for p in r.get("b58Purchases", []):
            sym = p.get("sym", "")
            buy_map[sym] = {
                "buy_mkt_pct":  float(str(p.get("mktPct", "0")).replace("%", "") or 0),
                "buy_amount_m": float(''.join(c for c in str(p.get("amount", "0")) if c.isdigit() or c == '.') or 0) / 1e6,
                "buy_kitta":    int(str(p.get("kitta", "0")).replace(",", "") or 0),
                "buy_avg_price": float(str(p.get("avgPrice", "0")).replace(",", "") or 0),
                "buy_txns":     int(str(p.get("txns", "0")).replace(",", "") or 0),
            }

        sell_map = {}
        for p in r.get("b58SalesList", []):
            sym = p.get("sym", "")
            sell_map[sym] = {
                "sell_mkt_pct":  float(str(p.get("mktPct", "0")).replace("%", "") or 0),
                "sell_amount_m": float(''.join(c for c in str(p.get("amount", "0")) if c.isdigit() or c == '.') or 0) / 1e6,
                "sell_kitta":    int(str(p.get("kitta", "0")).replace(",", "") or 0),
                "sell_avg_price": float(str(p.get("avgPrice", "0")).replace(",", "") or 0),
                "sell_txns":     int(str(p.get("txns", "0")).replace(",", "") or 0),
            }

        all_syms = set(buy_map) | set(sell_map)
        for sym in all_syms:
            b = buy_map.get(sym, {})
            s = sell_map.get(sym, {})
            row = {"date": date, "sym": sym}
            row.update({k: b.get(k, 0) for k in ("buy_mkt_pct", "buy_amount_m", "buy_kitta", "buy_avg_price", "buy_txns")})
            row.update({k: s.get(k, 0) for k in ("sell_mkt_pct", "sell_amount_m", "sell_kitta", "sell_avg_price", "sell_txns")})
            row["net_kitta"]   = row["buy_kitta"] - row["sell_kitta"]
            row["net_amount_m"] = row["buy_amount_m"] - row["sell_amount_m"]
            rows.append(row)

    df = pd.DataFrame(rows).sort_values(["sym", "date"]).reset_index(drop=True)
    return df


def build_subindex_df(reports: List[Dict]) -> pd.DataFrame:
    """Build sub-index daily DataFrame."""
    rows = []
    for r in reports:
        date = pd.to_datetime(r["_date"])
        for si in r.get("subIndices", []):
            rows.append({
                "date":      date,
                "name":      si.get("name", ""),
                "value":     float(str(si.get("value", "0")).replace(",", "") or 0),
                "chg":       float(str(si.get("chg", "0")).replace(",", "") or 0),
                "chg_pct":   float(str(si.get("chgPct", "0")).replace("%", "").replace("+", "") or 0),
                "direction": si.get("direction", ""),
            })
    return pd.DataFrame(rows).sort_values(["name", "date"]).reset_index(drop=True)


def build_movers_df(reports: List[Dict]) -> pd.DataFrame:
    """Build top gainers/losers/turnover DataFrame."""
    rows = []
    for r in reports:
        date = pd.to_datetime(r["_date"])
        for g in r.get("topGainers", []):
            rows.append({"date": date, "sym": g.get("sym", ""), "type": "gainer",
                         "close": float(str(g.get("close", "0")).replace(",", "") or 0),
                         "chg_pct": float(str(g.get("chgPct", "0")).replace("%", "").replace("+", "") or 0)})
        for g in r.get("topLosers", []):
            rows.append({"date": date, "sym": g.get("sym", ""), "type": "loser",
                         "close": float(str(g.get("close", "0")).replace(",", "") or 0),
                         "chg_pct": float(str(g.get("chgPct", "0")).replace("%", "") or 0)})
        for g in r.get("topTurnover", []):
            tov = str(g.get("turnover", "0"))
            import re as _re2
            _vm = _re2.search(r"(\d+(?:\.\d+)?)", tov)
            val = float(_vm.group(1)) if _vm else 0.0
            rows.append({"date": date, "sym": g.get("sym", ""), "type": "turnover",
                         "close": float(str(g.get("ltp", "0")).replace(",", "") or 0),
                         "chg_pct": val})
    return pd.DataFrame(rows).sort_values(["date", "type"]).reset_index(drop=True)


def load_all(dates: List[str] = DATES):
    """
    Master loader — returns all DataFrames as a dict.
    Usage:
        from data_loader import load_all
        data = load_all()
        df_market = data['market']
    """
    reports = fetch_all_reports(dates)
    print("Building DataFrames...")
    data = {
        "raw":      reports,
        "market":   build_market_df(reports),
        "technical": build_technical_df(reports),
        "b58":      build_b58_df(reports),
        "subindex": build_subindex_df(reports),
        "movers":   build_movers_df(reports),
    }
    print(f"  market:    {len(data['market'])} rows")
    print(f"  technical: {len(data['technical'])} rows")
    print(f"  b58:       {len(data['b58'])} rows")
    print(f"  subindex:  {len(data['subindex'])} rows")
    print(f"  movers:    {len(data['movers'])} rows")
    return data
