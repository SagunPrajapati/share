"""
NEPSE B58 Intelligence — Main Runner
Usage:
    python main.py                    # Full report + terminal summary
    python main.py --print-summary    # Terminal only (fast)
    python main.py --output out.html  # Custom output
"""
import argparse, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DATES
import data_loader as dl
import pandas as pd

def _load_local(dates):
    sd = os.path.dirname(os.path.abspath(__file__))
    dd = os.path.join(sd, "data")
    reports, found = [], 0
    print(f"Loading {len(dates)} local JSON files from {dd}/")
    for date in dates:
        path = os.path.join(dd, f"{date}.json")
        if os.path.exists(path):
            with open(path) as f: data = json.load(f)
            data["_date"] = date; reports.append(data); found += 1
            print(f"  ✓ {date}")
        else:
            print(f"  ✗ {date} (missing)")
    print(f"\nLoaded {found}/{len(dates)} reports.\n")
    return reports

def load_data(dates=None):
    if dates is None: dates = DATES
    reports = dl.fetch_all_reports(dates)
    if not reports:
        print("  → GitHub unreachable, trying local data/ directory...")
        reports = _load_local(dates)
    if not reports:
        print("❌ No data found. Place JSON files in nepse_analysis/data/"); sys.exit(1)
    dl.fetch_all_reports = lambda d=None: reports
    return dl.load_all(dates)

def print_summary(data):
    from analysis import (detect_market_regime, compute_decision_scores,
                          compute_b58_conviction, compute_b58_nepse_correlation,
                          get_rsi_trend)
    mdf = data["market"]; tdf = data["technical"]; bdf = data["b58"]
    regime = detect_market_regime(mdf)
    scores = compute_decision_scores(tdf, bdf, mdf)
    conv   = compute_b58_conviction(bdf, mdf)
    corr   = compute_b58_nepse_correlation(mdf)
    rsi    = get_rsi_trend(tdf)
    last   = mdf.iloc[-1]; first = mdf.iloc[0]; n = len(mdf)

    G="\033[92m"; R="\033[91m"; Y="\033[93m"; B="\033[94m"
    C="\033[96m"; M="\033[95m"; BLD="\033[1m"; DIM="\033[2m"; RST="\033[0m"
    W=60

    def bar(v,m=100,w=18): return "█"*int(v/m*w)+"░"*(w-int(v/m*w))

    print(f"\n{C}{'═'*W}{RST}")
    print(f"{BLD}{C}  NEPSE B58 INTELLIGENCE — PYTHON ANALYSIS{RST}")
    print(f"{DIM}  Broker 58 (Naasa Securities) · {n} Sessions · Python+Pandas+Plotly{RST}")
    print(f"{C}{'═'*W}{RST}\n")

    rc = G if "BULL" in regime["regime"] else R if "BEAR" in regime["regime"] else Y
    nd = last["nepse_close"] - first["nepse_close"]
    dc = G if nd >= 0 else R; nc = G if last["b58_net_m"]>=0 else R
    print(f"  {BLD}MARKET REGIME{RST}  {rc}{BLD}{regime['regime']}{RST}")
    print(f"  {'─'*W}")
    print(f"  NEPSE Close:    {BLD}{last['nepse_close']:>10,.2f}{RST}  {dc}{nd:>+.2f}{RST}")
    print(f"  B58 Net:        {nc}{BLD}₨{last['b58_net_m']:>+.1f}M{RST}  {last['b58_stance']}")
    print(f"  5D NEPSE Δ:     {dc}{regime['nepse_5d_chg']:>+.2f}%{RST}")
    print(f"  B58 Buy Rate:   {bar(regime['b58_buy_rate'])} {regime['b58_buy_rate']:.0f}%")
    print(f"  B58→NEPSE Corr: {corr['correlation']:>+.3f}  {DIM}({corr['interpretation']}){RST}")
    print()

    print(f"  {BLD}{G}🔥 TOP BUY SIGNALS{RST}")
    print(f"  {'─'*W}")
    buys = scores[scores["decision"].isin(["STRONG BUY","BUY/ADD"])].head(8)
    for _,r in buys.iterrows():
        fires="🔥"*min(int(r["buy_streak"])//3,3)
        sc=G if r["decision"]=="STRONG BUY" else "\033[38;5;82m"
        print(f"  {G}{r['sym']:<8}{RST} LTP:{r['ltp_latest']:>9,.0f} "
              f"RSI:{r['rsi_latest']:>5.1f} ADX:{r['adx_latest']:>5.1f} "
              f"Streak:{int(r['buy_streak']):>2}d Score:{r['total_score']:>5.0f} "
              f"{sc}{r['decision']}{RST}{fires}")
    if len(buys)==0: print(f"  {DIM}No strong buy signals{RST}")
    print()

    avoid = scores[scores["decision"]=="AVOID"].head(5)
    if len(avoid):
        print(f"  {BLD}{R}⚠️  AVOID / HIGH RISK{RST}")
        print(f"  {'─'*W}")
        for _,r in avoid.iterrows():
            reason=("Oversold" if r["rsi_latest"]<35 else "High Vol" if r["atr_latest"]>=40 else "Bearish")
            print(f"  {R}{r['sym']:<8}{RST} RSI:{r['rsi_latest']:.1f} ATR:{r['atr_latest']:.1f} "
                  f"Score:{r['total_score']:.0f} → {reason}")
        print()

    print(f"  {BLD}{M}💎 B58 CONVICTION LEADERS{RST}")
    print(f"  {'─'*W}")
    for _,r in conv.head(6).iterrows():
        streak=int(r["buy_streak"]) if pd.notna(r["buy_streak"]) else 0
        net=int(r["net_kitta"]) if pd.notna(r["net_kitta"]) else 0
        fires="🔥"*min(streak//3,3)
        print(f"  {M}{r['sym']:<8}{RST} Net:{net:>+9,}  Streak:{streak}d  "
              f"Mkt:{r['avg_buy_mkt_pct']:.1f}%  Score:{r['conviction_score']:.0f}{fires}")
    print()

    os_watch = rsi[rsi["rsi_latest"]<35]
    if len(os_watch):
        print(f"  {BLD}{Y}📉 OVERSOLD WATCH (RSI<35){RST}")
        for _,r in os_watch.iterrows():
            print(f"  {Y}{r['sym']:<8}{RST} RSI:{r['rsi_latest']:.1f} ADX:{r['adx_latest']:.1f} Zone:{r['zone']}")
        print()

    buy_days=int(mdf["is_b58_buyer"].sum()); total_net=mdf["b58_net_m"].sum()
    print(f"  {DIM}Sessions:{n}  B58 Buy:{buy_days}/{n}  Cum Net:₨{total_net:+.1f}M{RST}")
    print(f"{C}{'═'*W}{RST}\n")

def main():
    parser = argparse.ArgumentParser(description="NEPSE B58 Intelligence Suite")
    parser.add_argument("--dates", nargs="+", default=DATES)
    parser.add_argument("--output", default=None)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()

    if args.output is None:
        sd = os.path.dirname(os.path.abspath(__file__))
        args.output = os.path.join(sd, "..", "reports", "nepse_b58_report.html")

    data = load_data(args.dates)
    print_summary(data)

    if not args.print_summary:
        from report_generator import generate_report
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        path = generate_report(data, args.output)
        print(f"📂 Open in browser:\n   file://{os.path.abspath(path)}\n")

if __name__ == "__main__":
    main()
