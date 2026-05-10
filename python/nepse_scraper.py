"""
NEPSE Daily Data Extractor v3
================================
Uses Playwright to run inside the nepalstock.com.np browser context
where the WASM token generator is already loaded. Extracts the
Authorization token and uses it for all API calls.

Usage:
    python nepse_scraper.py                    # today
    python nepse_scraper.py --date 2026-05-08  # specific date
"""

import asyncio, json, re, os, argparse
from datetime import datetime, date
from pathlib import Path
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from playwright.async_api import async_playwright

OUTPUT_DIR = "."
BROKER_ID  = 58
BASE       = "https://nepalstock.com.np/api/nots"

WATCHLIST = [
    "NHPC","NABIL","NICA","NIFRA","GBIME",
    "SHIVM","LBBL","NRN","AKJCL","UPPER",
    "HIDCL","SWBBL","CHCL","SRBL","CZBIL",
    "SANIMA","PRVU","NBL","RLFL","NLBBL",
]

def log(msg): print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def safe_float(s):
    try: return float(str(s or "0").replace(",","").replace("Rs.","").replace("%","").strip())
    except: return 0.0

def fmt_rs(val):
    if val >= 1e9: return f"Rs.{val/1e9:.2f}B"
    if val >= 1e6: return f"Rs.{val/1e6:.2f}M"
    return f"Rs.{val:,.0f}"

async def get_auth_token(page):
    """Load NEPSE, wait for WASM, call generate_token, return Bearer token."""
    log("Loading NEPSE to get auth token via WASM...")
    await page.goto("https://nepalstock.com.np/today-price", timeout=60000)
    await page.wait_for_load_state("networkidle", timeout=60000)
    await asyncio.sleep(3)

    # Wait for WASM Module to be fully initialised with ccall
    token = await page.evaluate("""
        () => new Promise((resolve) => {
            const check = () => {
                if (typeof Module !== 'undefined' && typeof Module.ccall === 'function') {
                    try {
                        const today = new Date().toISOString().slice(0,10);
                        const tok = Module.ccall('generate_token','string',['string'],[today]);
                        if (tok && tok.length > 5) { resolve(tok); return; }
                        // try without date
                        const tok2 = Module.ccall('generate_token','string',[],[]);
                        resolve(tok2 || '');
                    } catch(e) { resolve('wasm_err:' + e.message); }
                } else {
                    setTimeout(check, 500);
                }
            };
            check();
            // timeout after 30s
            setTimeout(() => resolve('timeout'), 30000);
        })
    """)

    if token and not token.startswith('wasm_err') and token != 'timeout':
        log(f"   Token obtained via WASM: {token[:30]}...")
        return f"Bearer {token}"

    # Fallback: intercept a real API call from the page to capture the token
    log("   WASM approach failed, intercepting live API call...")
    captured = {}

    async def on_request(request):
        if "api/nots" in request.url and not captured.get("token"):
            auth = request.headers.get("authorization", "")
            if auth and auth.startswith("Bearer"):
                captured["token"] = auth
                captured["url"]   = request.url

    page.on("request", on_request)
    await page.reload()
    await page.wait_for_load_state("networkidle", timeout=30000)
    await asyncio.sleep(3)

    if captured.get("token"):
        log(f"   Token captured from live request: {captured['token'][:30]}...")
        return captured["token"]

    log("   Could not obtain token. Will try without auth.")
    return ""

async def api_get(session_token, url, params=None):
    """Make authenticated GET request."""
    import requests as req
    hdrs = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://nepalstock.com.np/",
    }
    if session_token:
        hdrs["Authorization"] = session_token
    try:
        r = req.get(url, headers=hdrs, params=params, timeout=30, verify=False)
        if r.status_code == 200:
            return r.json()
        log(f"   GET {url.split('/')[-1]} -> {r.status_code}")
    except Exception as e:
        log(f"   GET error {url}: {e}")
    return None

async def api_post(session_token, url, body=None):
    """Make authenticated POST request."""
    import requests as req
    hdrs = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Referer": "https://nepalstock.com.np/",
    }
    if session_token:
        hdrs["Authorization"] = session_token
    try:
        r = req.post(url, headers=hdrs, json=body or {}, timeout=30, verify=False)
        if r.status_code == 200:
            return r.json()
        log(f"   POST {url.split('/')[-1]} -> {r.status_code}")
    except Exception as e:
        log(f"   POST error {url}: {e}")
    return None

async def fetch_all_data(tok, report_date):
    """Fetch all NEPSE data using the auth token."""
    log("Fetching NEPSE index...")
    nepse_idx = await api_get(tok, f"{BASE}/nepse-index") or []
    main_idx = next((x for x in nepse_idx if x.get("index") == "NEPSE"), nepse_idx[0] if nepse_idx else {})
    close = str(round(safe_float(main_idx.get("currentValue",0)),2)) if main_idx else "—"
    chg   = safe_float(main_idx.get("change",0))
    pct   = safe_float(main_idx.get("perChange",0))
    sign  = "+" if chg >= 0 else ""
    chg_str = f"{sign}{chg:.2f} ({sign}{pct:.2f}%)" if main_idx else "—"
    log(f"   NEPSE: {close}  Chg: {chg_str}")

    log("Fetching market summary...")
    summary = await api_get(tok, f"{BASE}/market-summary/") or {}
    turnover     = fmt_rs(safe_float(summary.get("totalTurnover",0)))
    shares       = f"{int(safe_float(summary.get('totalTradedShares',0))):,}"
    transactions = f"{int(safe_float(summary.get('totalTransactions',0))):,}"
    adv          = summary.get("advancers","—"); dec = summary.get("decliners","—"); unc = summary.get("unchanged","—")
    adv_dec      = f"{adv} / {dec} / {unc}"
    market_cap   = fmt_rs(safe_float(summary.get("marketCap",0)))
    float_cap    = fmt_rs(safe_float(summary.get("floatMarketCap",0)))

    log("Fetching sub-indices...")
    sub_raw = await api_get(tok, f"{BASE}/nepse-index") or []
    sub_indices = []
    for x in sub_raw:
        nm = x.get("index","")
        if nm in ("","NEPSE","Float","Sensitive","Sensitive Float"): continue
        v = round(safe_float(x.get("currentValue",0)),2)
        c = round(safe_float(x.get("change",0)),2)
        p = round(safe_float(x.get("perChange",0)),2)
        s = "+" if c >= 0 else ""
        sub_indices.append({"name":nm,"value":str(v),"chg":f"{s}{c}","chgPct":f"{s}{p}%","direction":"up" if c>=0 else "down"})

    log("Fetching top movers...")
    gainers_raw  = await api_get(tok, f"{BASE}/top-ten/top-gainer?all=false") or []
    losers_raw   = await api_get(tok, f"{BASE}/top-ten/top-loser?all=false") or []
    turnover_raw = await api_get(tok, f"{BASE}/top-ten/turnover?all=false") or []
    volume_raw   = await api_get(tok, f"{BASE}/top-ten/trade?all=false") or []

    def mover(arr, keys):
        return [{"sym":x.get("symbol",""),"close":str(x.get(keys[0],"")),"chgPct":str(x.get(keys[1],""))} for x in arr[:10] if x.get("symbol")]

    gainers  = [{"sym":x.get("symbol",""),"close":str(x.get("ltp","")),"chgPct":f"+{x.get('percentageChange','')}%"} for x in gainers_raw[:10] if x.get("symbol")]
    losers   = [{"sym":x.get("symbol",""),"close":str(x.get("ltp","")),"chgPct":f"{x.get('percentageChange','')}%"} for x in losers_raw[:10] if x.get("symbol")]
    turnover = [{"sym":x.get("symbol",""),"ltp":str(x.get("ltp","")),"turnover":fmt_rs(safe_float(x.get("turnover","0")))} for x in turnover_raw[:10] if x.get("symbol")]
    volume   = [{"sym":x.get("symbol",""),"shares":str(x.get("totalTradedQuantity","")),"ltp":str(x.get("ltp",""))} for x in volume_raw[:10] if x.get("symbol")]
    log(f"   G:{len(gainers)} L:{len(losers)} T:{len(turnover)}")

    log(f"Fetching Broker {BROKER_ID} floorsheet...")
    b58_raw = await api_get(tok, f"{BASE}/securityDailyTradeStat/{BROKER_ID}") or []
    buy_map = {}; sell_map = {}

    for row in (b58_raw if isinstance(b58_raw,list) else []):
        sym = row.get("symbol","") or row.get("stockSymbol","")
        qty = int(safe_float(row.get("totalPurchaseQuantity",row.get("buyQuantity",0))))
        amt = safe_float(row.get("totalPurchaseAmount",row.get("buyAmount",0)))
        avg = safe_float(row.get("buyAveragePrice",0))
        sqty = int(safe_float(row.get("totalSalesQuantity",row.get("sellQuantity",0))))
        samt = safe_float(row.get("totalSalesAmount",row.get("sellAmount",0)))
        savg = safe_float(row.get("sellAveragePrice",0))
        if sym and qty > 0:
            buy_map[sym] = {"kitta":qty,"amount":amt,"avg":avg}
        if sym and sqty > 0:
            sell_map[sym] = {"kitta":sqty,"amount":samt,"avg":savg}

    # If securityDailyTradeStat didn't give buy/sell breakdown, try the direct floorsheet
    if not buy_map and not sell_map:
        log("   Trying broker floorsheet endpoint...")
        fs = await api_get(tok, f"{BASE}/security/broker-floorsheet/{BROKER_ID}",{"size":500,"businessDate":""}) or {}
        sheets = fs.get("floorsheets",fs.get("content",[])) if isinstance(fs,dict) else (fs if isinstance(fs,list) else [])
        for row in sheets:
            sym = row.get("stockSymbol","")
            qty = int(safe_float(row.get("contractQuantity",0)))
            amt = safe_float(row.get("contractAmount",0))
            avg = safe_float(row.get("contractRate",0))
            buyer = str(row.get("buyerBrokerCode",""))
            seller= str(row.get("sellerBrokerCode",""))
            if buyer == str(BROKER_ID):
                if sym not in buy_map: buy_map[sym]={"kitta":0,"amount":0,"avg":avg}
                buy_map[sym]["kitta"]+=qty; buy_map[sym]["amount"]+=amt
            if seller == str(BROKER_ID):
                if sym not in sell_map: sell_map[sym]={"kitta":0,"amount":0,"avg":avg}
                sell_map[sym]["kitta"]+=qty; sell_map[sym]["amount"]+=amt

    buy_total  = sum(v["amount"] for v in buy_map.values())
    sell_total = sum(v["amount"] for v in sell_map.values())
    net = buy_total - sell_total
    sign = "+" if net >= 0 else ""
    b58_purchases = [{"sym":s,"mktPct":"—","amount":fmt_rs(v["amount"]),"kitta":f"{v['kitta']:,}","avgPrice":str(round(v['avg'],2)),"txns":"—"} for s,v in sorted(buy_map.items(),key=lambda x:-x[1]["amount"])[:20]]
    b58_sales     = [{"sym":s,"mktPct":"—","amount":fmt_rs(v["amount"]),"kitta":f"{v['kitta']:,}","avgPrice":str(round(v['avg'],2)),"txns":"—"} for s,v in sorted(sell_map.items(),key=lambda x:-x[1]["amount"])[:20]]
    all_syms = set(list(buy_map)+list(sell_map))
    net_accum = []
    for sym in all_syms:
        b=buy_map.get(sym,{}).get("kitta",0); s=sell_map.get(sym,{}).get("kitta",0); nk=b-s
        rating="★★★" if abs(nk)>50000 else "★★" if abs(nk)>10000 else "★"
        net_accum.append({"sym":sym,"netKitta":f"+{nk:,}" if nk>=0 else f"{nk:,}","sellMktPct":"—","convWidth":str(min(100,max(10,abs(nk)//500))),"rating":rating,"note":f"B58 {'accumulating' if nk>=0 else 'distributing'} {abs(nk):,} net kitta"})
    net_accum.sort(key=lambda x: int(x["netKitta"].replace("+","").replace(",","")),reverse=True)
    log(f"   Buy:{fmt_rs(buy_total)} Sell:{fmt_rs(sell_total)} Net:{sign}{fmt_rs(abs(net))}")
    log(f"   Purchases:{len(b58_purchases)} Sales:{len(b58_sales)}")

    log("Fetching technicals...")
    today_price = await api_post(tok, f"{BASE}/nepse-data/today-price?",
        {"id":58,"size":500,"page":0,"sortBy":"","sortAsc":True,"sector":"","isNonDelisted":True,"businessDate":""}) or {}
    price_map = {s.get("symbol",""):s for s in today_price.get("content",today_price if isinstance(today_price,list) else [])}

    technical = []
    for sym in WATCHLIST:
        s = price_map.get(sym,{})
        ltp  = str(s.get("closingPrice","—"))
        w52h = str(s.get("fiftyTwoWeekHigh","—"))
        w52l = str(s.get("fiftyTwoWeekLow","—"))
        chg_pct = s.get("percentageChange","—")
        chg_s = f"+{chg_pct:.2f}%" if isinstance(chg_pct,(int,float)) and chg_pct>=0 else f"{chg_pct:.2f}%" if isinstance(chg_pct,(int,float)) else "—"
        ltp_f = safe_float(ltp)
        signal,action = "Neutral","WATCH"
        technical.append({"sym":sym,"ltp":ltp,"w52h":w52h,"w52l":w52l,"chg":chg_s,"rsi":"—","adx":"—","atr":"—","aroon":"—","adOsc":"—","signal":signal,"action":action})

    nepse_data = {"nepseClose":close,"nepseChg":chg_str,"turnover":turnover,"sharesTraded":shares,"transactions":transactions,"advDecUnch":adv_dec,"marketCap":market_cap,"floatCap":float_cap,"subIndices":sub_indices,"topGainers":gainers,"topLosers":losers,"topTurnover":turnover_raw_fmt if False else turnover,"topVolume":volume}
    b58_data = {"b58Stance":"NET BUYER" if net>=0 else "NET SELLER","b58Net":f"{sign}{fmt_rs(abs(net))}","b58Purchase":fmt_rs(buy_total),"b58SalesTotal":fmt_rs(sell_total),"b58Purchases":b58_purchases,"b58SalesList":b58_sales,"netAccum":net_accum}
    return nepse_data, b58_data, technical

def build_trade_plan(technical, net_accum):
    accum_map = {n["sym"]:n["netKitta"] for n in net_accum}
    plan=[]
    adds=sorted([t for t in technical if "ADD" in t.get("action","").upper()],key=lambda t:safe_float(t.get("adx","0")),reverse=True)
    for i,t in enumerate(adds[:15],1):
        ltp=safe_float(t["ltp"]); atr=safe_float(t["atr"])
        if ltp<=0: continue
        stop=round(ltp-(1.5*atr),2) if atr>0 else round(ltp*0.92,2)
        t1,t2,t3=round(ltp*1.12,2),round(ltp*1.20,2),round(ltp*1.30,2)
        risk=ltp-stop; reward=t1-ltp
        rr=f"1:{round(reward/risk,1)}" if risk>0 else "1:2.0"
        nk=accum_map.get(t["sym"],"—")
        plan.append({"rk":str(i),"sym":t["sym"],"ltp":t["ltp"],"w52hl":f"{t['w52h']}/{t['w52l']}","entry":f"{round(ltp*0.99,2)}-{round(ltp*1.01,2)}","stop":str(stop),"t1":str(t1),"t2":str(t2),"t3":str(t3),"rr":rr,"action":f"ADD — B58 {nk}" if nk!="—" else "ADD"})
    return plan

def build_action_plan(technical, net_accum):
    accum_map={n["sym"]:n for n in net_accum}
    order={"URGENT":0,"MONITOR":1,"WATCH":2,"AVOID":3}
    plan=[]
    for t in technical:
        action=t.get("action","WATCH").upper(); sym=t["sym"]; nk=(accum_map.get(sym) or {}).get("netKitta","—")
        if "ADD" in action: pri,pt,note="URGENT","urgent",f"B58 {nk}. ADD." if nk!="—" else "ADD signal."
        elif "HOLD" in action: pri,pt,note="MONITOR","monitor",f"Hold. RSI {t.get('rsi','—')}."
        elif "AVOID" in action: pri,pt,note="AVOID","avoid-row","Overbought/bearish."
        else: pri,pt,note="WATCH","watch","Watch for entry."
        plan.append({"priority":pri,"sym":sym,"ltp":t["ltp"],"w52h":t["w52h"],"action":action,"note":note,"type":pt})
    plan.sort(key=lambda x:order.get(x["priority"],99))
    return plan

def build_key_insights(nepse_data, b58_data, technical):
    ins=[]
    stance=b58_data.get("b58Stance","—"); net=b58_data.get("b58Net","—")
    top_buy=b58_data["b58Purchases"][0]["sym"] if b58_data.get("b58Purchases") else "—"
    ins.append({"num":"1","title":f"B58 is a {stance} — {net}","body":f"Broker 58 net {net}. Top buy: {top_buy}. {'Accumulation signals confidence.' if 'BUYER' in stance else 'Distribution — proceed with caution.'}"})
    chg=nepse_data.get("nepseChg",""); adv=nepse_data.get("advDecUnch","—")
    ins.append({"num":"2","title":f"NEPSE {'rallied' if '+' in chg else 'declined'} {chg}","body":f"A/D/U: {adv}. Turnover: {nepse_data.get('turnover','—')}."})
    return ins

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date",     default=date.today().strftime("%Y-%m-%d"))
    parser.add_argument("--no-alpha", action="store_true")
    args = parser.parse_args()
    report_date = args.date.strip()
    log(f"=== NEPSE Extractor v3 — {report_date} ===")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36", viewport={"width":1280,"height":900})
        page = await context.new_page()
        await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf}", lambda r: r.abort())

        tok = await get_auth_token(page)
        await browser.close()

    nepse_data, b58_data, technical = await fetch_all_data(tok, report_date)

    trade_plan   = build_trade_plan(technical, b58_data.get("netAccum",[]))
    action_plan  = build_action_plan(technical, b58_data.get("netAccum",[]))
    key_insights = build_key_insights(nepse_data, b58_data, technical)

    chg=nepse_data.get("nepseChg",""); stance=b58_data.get("b58Stance","—")
    headline = ("STRONG GREEN / B58 Accumulating" if "+" in chg and "BUYER" in stance else
                "GREEN / Cautious Rally" if "+" in chg else
                "MIXED / B58 Buying on Dip" if stance=="NET BUYER" else
                "RED / Distribution Pressure")

    b58p = b58_data.get("b58Purchases",[])
    report = {
        "date":report_date,"headline":headline,
        "nepseClose":nepse_data.get("nepseClose","—"),"nepseChg":nepse_data.get("nepseChg","—"),
        "turnover":nepse_data.get("turnover","—"),"sharesTraded":nepse_data.get("sharesTraded","—"),
        "transactions":nepse_data.get("transactions","—"),"advDecUnch":nepse_data.get("advDecUnch","—"),
        "marketCap":nepse_data.get("marketCap","—"),"floatCap":nepse_data.get("floatCap","—"),
        "b58Stance":b58_data.get("b58Stance","—"),"b58Net":b58_data.get("b58Net","—"),
        "b58Purchase":b58_data.get("b58Purchase","—"),"b58SalesTotal":b58_data.get("b58SalesTotal","—"),
        "b58TopBuy":b58p[0]["sym"] if b58p else "—","b58PeakMkt":b58p[0].get("mktPct","—") if b58p else "—",
        "marketPulseNote":f"NEPSE {nepse_data.get('nepseClose','—')} ({nepse_data.get('nepseChg','—')}) turnover {nepse_data.get('turnover','—')}. B58 {b58_data.get('b58Stance','—')} {b58_data.get('b58Net','—')}.",
        "subIndices":nepse_data.get("subIndices",[]),
        "topGainers":nepse_data.get("topGainers",[]),"topLosers":nepse_data.get("topLosers",[]),
        "topTurnover":nepse_data.get("topTurnover",[]),"topVolume":nepse_data.get("topVolume",[]),
        "b58Purchases":b58_data.get("b58Purchases",[]),"b58SalesList":b58_data.get("b58SalesList",[]),
        "netAccum":b58_data.get("netAccum",[]),"technical":technical,
        "tradePlan":trade_plan,"keyInsights":key_insights,"actionPlan":action_plan,
        "disclaimer":["Not financial advice — personal tracking only.","Data: nepalstock.com.np",f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} NPT"],
    }

    out = Path(OUTPUT_DIR) / f"{report_date}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out,"w",encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    log(f"Saved: {out}  NEPSE:{report['nepseClose']}  B58:{report['b58Stance']} {report['b58Net']}  Stocks:{len(technical)}")
    log("=== Done ===")

if __name__ == "__main__":
    asyncio.run(main())
