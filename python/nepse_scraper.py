"""
NEPSE Daily Data Extractor v2
================================
Uses NEPSE's own JSON API endpoints — much faster and more reliable than scraping.
NEPSE Alpha technicals are fetched via API too (no browser needed).

Usage:
    python nepse_scraper.py                    # today
    python nepse_scraper.py --date 2026-05-10  # specific date
    python nepse_scraper.py --no-alpha         # skip technicals
"""

import asyncio, json, re, os, argparse, sys
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from datetime import datetime, date
from pathlib import Path

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ── CONFIG ──────────────────────────────────────────────────
BROKER_ID   = 58          # Naasa Securities = 58
OUTPUT_DIR  = "."         # where to save YYYY-MM-DD.json
TIMEOUT     = 30          # requests timeout in seconds
HEADERS     = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":     "application/json, text/plain, */*",
    "Referer":    "https://nepalstock.com.np/",
}
WATCHLIST = [
    "NHPC","NABIL","NICA","NIFRA","GBIME",
    "SHIVM","LBBL","NRN","AKJCL","UPPER",
    "HIDCL","SWBBL","CHCL","SRBL","CZBIL",
    "SANIMA","PRVU","NBL","RLFL","NLBBL",
]

BASE = "https://nepalstock.com.np/api/nots"

# ── HELPERS ─────────────────────────────────────────────────
def log(msg): print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def safe_float(s):
    try: return float(str(s or "0").replace(",","").replace("Rs.","").replace("%","").strip())
    except: return 0.0

def fmt_rs(val):
    if val >= 1e9: return f"Rs.{val/1e9:.2f}B"
    if val >= 1e6: return f"Rs.{val/1e6:.2f}M"
    return f"Rs.{val:,.0f}"

def get(url, params=None):
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=TIMEOUT, verify=False)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log(f"   GET failed {url}: {e}")
        return None

# ── 1. NEPSE INDEX ───────────────────────────────────────────
def fetch_nepse_index():
    log("Fetching NEPSE index...")
    data = {}
    d = get(f"{BASE}/index")
    if d:
        try:
            idx = next((x for x in d if x.get("index") == "NEPSE"), d[0] if d else {})
            data["nepseClose"] = str(round(safe_float(idx.get("currentValue", 0)), 2))
            chg = safe_float(idx.get("change", 0))
            pct = safe_float(idx.get("perChange", 0))
            sign = "+" if chg >= 0 else ""
            data["nepseChg"] = f"{sign}{chg:.2f} ({sign}{pct:.2f}%)"
            log(f"   NEPSE: {data['nepseClose']}  Chg: {data['nepseChg']}")
        except Exception as e:
            log(f"   Index parse error: {e}")
    return data

# ── 2. MARKET SUMMARY ────────────────────────────────────────
def fetch_market_summary():
    log("Fetching market summary...")
    data = {}
    d = get(f"{BASE}/market/turnover")
    if d:
        try:
            data["turnover"]    = fmt_rs(safe_float(d.get("totalTurnover", 0)))
            data["sharesTraded"] = f"{int(safe_float(d.get('totalTradedShares', 0))):,}"
            data["transactions"] = f"{int(safe_float(d.get('totalTransactions', 0))):,}"
            adv = d.get("advancers", "—"); dec = d.get("decliners", "—"); unc = d.get("unchanged", "—")
            data["advDecUnch"]  = f"{adv} / {dec} / {unc}"
            data["marketCap"]   = fmt_rs(safe_float(d.get("marketCap", 0)))
            data["floatCap"]    = fmt_rs(safe_float(d.get("floatMarketCap", 0)))
            log(f"   Turnover:{data['turnover']}  A/D/U:{data['advDecUnch']}")
        except Exception as e:
            log(f"   Summary parse error: {e}")
    return data

# ── 3. SUB-INDICES ───────────────────────────────────────────
def fetch_sub_indices():
    log("Fetching sub-indices...")
    d = get(f"{BASE}/index")
    sub = []
    if d:
        for idx in d:
            name = idx.get("index", "")
            if name in ("", "NEPSE", "Float", "Sensitive", "Sensitive Float"): continue
            val  = round(safe_float(idx.get("currentValue", 0)), 2)
            chg  = round(safe_float(idx.get("change", 0)), 2)
            pct  = round(safe_float(idx.get("perChange", 0)), 2)
            sign = "+" if chg >= 0 else ""
            sub.append({"name": name, "value": str(val), "chg": f"{sign}{chg}", "chgPct": f"{sign}{pct}%", "direction": "up" if chg >= 0 else "down"})
        log(f"   Sub-indices: {len(sub)}")
    return sub

# ── 4. TOP MOVERS ────────────────────────────────────────────
def fetch_top_movers():
    log("Fetching top movers...")
    gainers, losers, turnover, volume = [], [], [], []
    d = get(f"{BASE}/market/today-price", {"size": 200, "businessDate": "", "sort": "percentageChange", "sortType": "desc"})
    if d and "content" in d:
        stocks = d["content"]
        sorted_up   = sorted(stocks, key=lambda x: safe_float(x.get("percentageChange", 0)), reverse=True)
        sorted_down = sorted(stocks, key=lambda x: safe_float(x.get("percentageChange", 0)))
        sorted_turn = sorted(stocks, key=lambda x: safe_float(x.get("turnover", 0)), reverse=True)
        sorted_vol  = sorted(stocks, key=lambda x: safe_float(x.get("totalTradedQuantity", 0)), reverse=True)
        for s in sorted_up[:10]:
            gainers.append({"sym": s.get("symbol",""), "close": str(s.get("closingPrice","")), "chgPct": f"+{safe_float(s.get('percentageChange',0)):.2f}%"})
        for s in sorted_down[:10]:
            losers.append({"sym": s.get("symbol",""), "close": str(s.get("closingPrice","")), "chgPct": f"{safe_float(s.get('percentageChange',0)):.2f}%"})
        for s in sorted_turn[:10]:
            turnover.append({"sym": s.get("symbol",""), "ltp": str(s.get("closingPrice","")), "turnover": fmt_rs(safe_float(s.get("turnover",0)))})
        for s in sorted_vol[:10]:
            volume.append({"sym": s.get("symbol",""), "shares": f"{int(safe_float(s.get('totalTradedQuantity',0))):,}", "ltp": str(s.get("closingPrice",""))})
        log(f"   Gainers:{len(gainers)} Losers:{len(losers)} Turnover:{len(turnover)}")
    return gainers, losers, turnover, volume

# ── 5. BROKER 58 FLOORSHEET ──────────────────────────────────
def fetch_broker58(business_date=""):
    log(f"Fetching Broker {BROKER_ID} floorsheet...")
    result = {"b58Stance":"—","b58Net":"—","b58Purchase":"—","b58SalesTotal":"—","b58Purchases":[],"b58SalesList":[],"netAccum":[]}

    # Get broker summary
    d = get(f"{BASE}/security/broker-floorsheet/{BROKER_ID}", {"size": 500, "businessDate": business_date})
    if not d:
        # Try without date
        d = get(f"{BASE}/security/broker-floorsheet/{BROKER_ID}", {"size": 500})
    if not d:
        log("   Broker API not available — trying floorsheet search...")
        d = get(f"{BASE}/floorsheet", {"brokerNumber": BROKER_ID, "size": 500})

    buy_map  = {}
    sell_map = {}

    if d and ("floorsheets" in d or "content" in d or isinstance(d, list)):
        sheets = d.get("floorsheets", d.get("content", d if isinstance(d, list) else []))
        log(f"   Raw floorsheet rows: {len(sheets)}")
        for row in sheets:
            sym      = row.get("stockSymbol", row.get("symbol", ""))
            qty      = int(safe_float(row.get("contractQuantity", row.get("quantity", 0))))
            amount   = safe_float(row.get("contractAmount", row.get("amount", 0)))
            avg_pr   = round(safe_float(row.get("contractRate", row.get("rate", 0))), 2)
            buyer_br = str(row.get("buyerBrokerCode", row.get("buyerBroker", "")))
            seller_br= str(row.get("sellerBrokerCode", row.get("sellerBroker", "")))

            if buyer_br == str(BROKER_ID):
                if sym not in buy_map: buy_map[sym] = {"kitta":0,"amount":0.0,"prices":[],"txns":0}
                buy_map[sym]["kitta"]  += qty
                buy_map[sym]["amount"] += amount
                buy_map[sym]["prices"].append(avg_pr)
                buy_map[sym]["txns"]   += 1

            if seller_br == str(BROKER_ID):
                if sym not in sell_map: sell_map[sym] = {"kitta":0,"amount":0.0,"prices":[],"txns":0}
                sell_map[sym]["kitta"]  += qty
                sell_map[sym]["amount"] += amount
                sell_map[sym]["prices"].append(avg_pr)
                sell_map[sym]["txns"]   += 1

    # Compute totals
    buy_total  = sum(v["amount"] for v in buy_map.values())
    sell_total = sum(v["amount"] for v in sell_map.values())
    net        = buy_total - sell_total

    result["b58Purchase"]   = fmt_rs(buy_total)
    result["b58SalesTotal"] = fmt_rs(sell_total)
    result["b58Net"]        = f"+{fmt_rs(net)}" if net >= 0 else fmt_rs(net).replace("Rs.","-Rs.")
    result["b58Stance"]     = "NET BUYER" if net >= 0 else "NET SELLER"

    # Build top purchases list (sorted by amount)
    for sym, v in sorted(buy_map.items(), key=lambda x: x[1]["amount"], reverse=True)[:20]:
        avg = round(sum(v["prices"])/len(v["prices"]),2) if v["prices"] else 0
        total = buy_map.get(sym,{}).get("amount",0) + sell_map.get(sym,{}).get("amount",0)
        mkt_pct = f"{round(v['amount']/(total)*100,2)}%" if total > 0 else "—"
        result["b58Purchases"].append({"sym":sym,"mktPct":mkt_pct,"amount":fmt_rs(v["amount"]),"kitta":f"{v['kitta']:,}","avgPrice":str(avg),"txns":str(v["txns"])})

    # Build top sales list
    for sym, v in sorted(sell_map.items(), key=lambda x: x[1]["amount"], reverse=True)[:20]:
        avg = round(sum(v["prices"])/len(v["prices"]),2) if v["prices"] else 0
        total = buy_map.get(sym,{}).get("amount",0) + sell_map.get(sym,{}).get("amount",0)
        mkt_pct = f"{round(v['amount']/(total)*100,2)}%" if total > 0 else "—"
        result["b58SalesList"].append({"sym":sym,"mktPct":mkt_pct,"amount":fmt_rs(v["amount"]),"kitta":f"{v['kitta']:,}","avgPrice":str(avg),"txns":str(v["txns"])})

    # Net accumulation
    all_syms = set(list(buy_map.keys()) + list(sell_map.keys()))
    net_accum = []
    for sym in all_syms:
        b_k = buy_map.get(sym,{}).get("kitta",0)
        s_k = sell_map.get(sym,{}).get("kitta",0)
        net_k = b_k - s_k
        conviction = min(100, max(10, abs(net_k)//500))
        rating = "★★★" if abs(net_k)>50000 else "★★" if abs(net_k)>10000 else "★"
        sell_pct = next((x["mktPct"] for x in result["b58SalesList"] if x["sym"]==sym),"—")
        net_accum.append({"sym":sym,"netKitta":f"+{net_k:,}" if net_k>=0 else f"{net_k:,}","sellMktPct":sell_pct,"convWidth":str(conviction),"rating":rating,"note":f"B58 {'accumulating' if net_k>=0 else 'distributing'} {abs(net_k):,} net kitta"})
    net_accum.sort(key=lambda x: int(x["netKitta"].replace("+","").replace(",","")), reverse=True)
    result["netAccum"] = net_accum

    log(f"   Buy:{result['b58Purchase']}  Sell:{result['b58SalesTotal']}  Net:{result['b58Net']}")
    log(f"   Purchases:{len(result['b58Purchases'])}  Sales:{len(result['b58SalesList'])}  Net accum:{len(net_accum)}")
    return result

# ── 6. TECHNICAL — via NEPSE API (no Alpha needed) ──────────
def fetch_technical(watchlist):
    log(f"Fetching technicals for {len(watchlist)} stocks via NEPSE API...")
    technical = []
    # Grab all today prices once
    d = get(f"{BASE}/market/today-price", {"size": 500})
    price_map = {}
    if d and "content" in d:
        for s in d["content"]:
            price_map[s.get("symbol","")] = s

    for sym in watchlist:
        s = price_map.get(sym, {})
        ltp  = str(s.get("closingPrice", "—"))
        w52h = str(s.get("fiftyTwoWeekHigh", "—"))
        w52l = str(s.get("fiftyTwoWeekLow", "—"))
        chg  = s.get("percentageChange", "—")
        chg_str = f"+{chg:.2f}%" if isinstance(chg,(int,float)) and chg>=0 else f"{chg:.2f}%" if isinstance(chg,(int,float)) else "—"

        # Get detailed security info for RSI/ADX if available
        det = get(f"{BASE}/security/{sym}")
        rsi=adx=atr=aroon="—"; ad_osc="—"
        if det:
            rsi    = str(round(safe_float(det.get("rsi14","—")),2))    if det.get("rsi14")    else "—"
            adx    = str(round(safe_float(det.get("adx14","—")),2))    if det.get("adx14")    else "—"
            atr    = str(round(safe_float(det.get("atr14","—")),2))    if det.get("atr14")    else "—"
            aroon  = str(round(safe_float(det.get("aroonUp","—")),2))  if det.get("aroonUp")  else "—"
            if aroon != "—": aroon += "%"

        rsi_f = safe_float(rsi); adx_f = safe_float(adx)
        signal,action = "Neutral","WATCH"
        if rsi_f>70:  signal,action = "Overbought","AVOID"
        elif rsi_f>55 and adx_f>25: signal,action = "Bullish","ADD"
        elif rsi_f>50: signal,action = "Mild Bullish","HOLD"
        elif rsi_f<30: signal,action = "Oversold","WATCH"
        elif rsi_f<45 and adx_f>25: signal,action = "Bearish","AVOID"

        technical.append({"sym":sym,"ltp":ltp,"w52h":w52h,"w52l":w52l,"chg":chg_str,"rsi":rsi,"adx":adx,"atr":atr,"aroon":aroon,"adOsc":ad_osc,"signal":signal,"action":action})

    log(f"   Technicals done: {len(technical)} stocks")
    return technical

# ── 7. DERIVED DATA ──────────────────────────────────────────
def build_trade_plan(technical, net_accum):
    accum_map = {n["sym"]: n["netKitta"] for n in net_accum}
    plan = []
    adds = sorted([t for t in technical if "ADD" in t.get("action","").upper()], key=lambda t: safe_float(t.get("adx","0")), reverse=True)
    for i,t in enumerate(adds[:15],1):
        ltp=safe_float(t["ltp"]); atr=safe_float(t["atr"])
        if ltp<=0: continue
        stop = round(ltp-(1.5*atr),2) if atr>0 else round(ltp*0.92,2)
        t1,t2,t3 = round(ltp*1.12,2),round(ltp*1.20,2),round(ltp*1.30,2)
        risk=ltp-stop; reward=t1-ltp
        rr = f"1:{round(reward/risk,1)}" if risk>0 else "1:2.0"
        nk = accum_map.get(t["sym"],"—")
        plan.append({"rk":str(i),"sym":t["sym"],"ltp":t["ltp"],"w52hl":f"{t['w52h']}/{t['w52l']}","entry":f"{round(ltp*0.99,2)}-{round(ltp*1.01,2)}","stop":str(stop),"t1":str(t1),"t2":str(t2),"t3":str(t3),"rr":rr,"action":f"ADD — B58 {nk}" if nk!="—" else "ADD — Technical"})
    return plan

def build_action_plan(technical, net_accum):
    accum_map = {n["sym"]:n for n in net_accum}
    order={"URGENT":0,"MONITOR":1,"WATCH":2,"AVOID":3}
    plan=[]
    for t in technical:
        action=t.get("action","WATCH").upper(); sym=t["sym"]; nk=(accum_map.get(sym) or {}).get("netKitta","—")
        if "ADD" in action or "BUY" in action: pri,pt,note="URGENT","urgent",f"B58 {nk}. ADD on pullback." if nk!="—" else "Strong signal. ADD."
        elif "HOLD" in action: pri,pt,note="MONITOR","monitor",f"Hold. RSI {t.get('rsi','—')}."
        elif "AVOID" in action: pri,pt,note="AVOID","avoid-row",f"RSI {t.get('rsi','—')} overbought/bearish."
        else: pri,pt,note="WATCH","watch",f"Watch. ADX {t.get('adx','—')}."
        plan.append({"priority":pri,"sym":sym,"ltp":t["ltp"],"w52h":t["w52h"],"action":action,"note":note,"type":pt})
    plan.sort(key=lambda x: order.get(x["priority"],99))
    return plan

def build_key_insights(nepse_data, b58, technical):
    ins=[]
    stance=b58.get("b58Stance","—"); net=b58.get("b58Net","—")
    top_buy=b58["b58Purchases"][0]["sym"] if b58.get("b58Purchases") else "—"
    ins.append({"num":"1","title":f"B58 is a {stance} — {net}","body":f"Broker 58 net {net}. Top buy: {top_buy}. {'Accumulation signals confidence.' if 'BUYER' in stance else 'Distribution — proceed with caution.'}"})
    chg=nepse_data.get("nepseChg",""); adv=nepse_data.get("advDecUnch","—")
    ins.append({"num":"2","title":f"NEPSE {'rallied' if '+' in chg else 'declined'} {chg}","body":f"A/D/U: {adv}. Turnover: {nepse_data.get('turnover','—')}."})
    strong=[t for t in technical if safe_float(t.get("rsi","0"))>55 and safe_float(t.get("adx","0"))>25]
    if strong: ins.append({"num":"3","title":f"Strong confluence: {', '.join(t['sym'] for t in strong[:5])}","body":"RSI>55 and ADX>25. Scale in on pullbacks."})
    ob=[t for t in technical if safe_float(t.get("rsi","0"))>70]
    if ob: ins.append({"num":"4","title":f"Overbought: {', '.join(t['sym'] for t in ob[:3])}","body":"RSI>70. Avoid chasing — wait for RSI<65."})
    return ins

# ── MAIN ─────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date",     default=date.today().strftime("%Y-%m-%d"))
    parser.add_argument("--no-alpha", action="store_true")
    parser.add_argument("--stocks",   default="")
    args = parser.parse_args()

    report_date = args.date.strip()
    watchlist   = [s.strip().upper() for s in args.stocks.split(",")] if args.stocks else WATCHLIST
    log(f"=== NEPSE Extractor v2 — {report_date} ===")

    nepse   = fetch_nepse_index()
    summary = fetch_market_summary()
    nepse.update(summary)
    sub_idx = fetch_sub_indices()
    gainers, losers, turnover, volume = fetch_top_movers()
    b58     = fetch_broker58()
    tech    = [] if args.no_alpha else fetch_technical(watchlist)

    trade_plan   = build_trade_plan(tech, b58.get("netAccum",[]))
    action_plan  = build_action_plan(tech, b58.get("netAccum",[]))
    key_insights = build_key_insights(nepse, b58, tech)

    chg = nepse.get("nepseChg",""); stance = b58.get("b58Stance","—")
    headline = ("STRONG GREEN / B58 Accumulating" if "+" in chg and "BUYER" in stance
                else "GREEN / Cautious Rally"     if "+" in chg
                else "MIXED / B58 Buying on Dip"  if stance=="NET BUYER"
                else "RED / Distribution Pressure")

    report = {
        "date":            report_date,
        "headline":        headline,
        "nepseClose":      nepse.get("nepseClose","—"),
        "nepseChg":        nepse.get("nepseChg","—"),
        "turnover":        nepse.get("turnover","—"),
        "sharesTraded":    nepse.get("sharesTraded","—"),
        "transactions":    nepse.get("transactions","—"),
        "advDecUnch":      nepse.get("advDecUnch","—"),
        "marketCap":       nepse.get("marketCap","—"),
        "floatCap":        nepse.get("floatCap","—"),
        "b58Stance":       b58.get("b58Stance","—"),
        "b58Net":          b58.get("b58Net","—"),
        "b58Purchase":     b58.get("b58Purchase","—"),
        "b58SalesTotal":   b58.get("b58SalesTotal","—"),
        "b58TopBuy":       b58["b58Purchases"][0]["sym"] if b58.get("b58Purchases") else "—",
        "b58PeakMkt":      b58["b58Purchases"][0]["mktPct"] if b58.get("b58Purchases") else "—",
        "marketPulseNote": f"NEPSE closed at {nepse.get('nepseClose','—')} ({nepse.get('nepseChg','—')}) with turnover {nepse.get('turnover','—')}. Broker 58 was a {b58.get('b58Stance','—')} with net {b58.get('b58Net','—')}.",
        "subIndices":      sub_idx,
        "topGainers":      gainers,
        "topLosers":       losers,
        "topTurnover":     turnover,
        "topVolume":       volume,
        "b58Purchases":    b58.get("b58Purchases",[]),
        "b58SalesList":    b58.get("b58SalesList",[]),
        "netAccum":        b58.get("netAccum",[]),
        "technical":       tech,
        "tradePlan":       trade_plan,
        "keyInsights":     key_insights,
        "actionPlan":      action_plan,
        "disclaimer":      ["Not financial advice — personal tracking only.", "Data: nepalstock.com.np", f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} NPT"],
    }

    out = Path(OUTPUT_DIR) / f"{report_date}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out,"w",encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    log(f"Saved: {out}  NEPSE:{report['nepseClose']}  B58:{report['b58Stance']} {report['b58Net']}  Stocks:{len(tech)}")
    log("=== Done ===")

if __name__ == "__main__":
    main()
