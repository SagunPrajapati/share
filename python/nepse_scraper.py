"""
NEPSE Daily Data Extractor v3
================================
Uses Playwright to load nepalstock.com.np, intercepts the Authorization
token from live API calls (WASM-generated), then fetches all data.

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
    import requests as req_lib
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from playwright.async_api import async_playwright

OUTPUT_DIR = "."
BROKER_ID  = 58
BASE       = "https://nepalstock.com.np/api/nots"
TIMEOUT    = 30

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

def api_get(token, url, params=None):
    hdrs = {"User-Agent":"Mozilla/5.0","Accept":"application/json, text/plain, */*","Referer":"https://nepalstock.com.np/"}
    if token: hdrs["Authorization"] = token
    try:
        r = req_lib.get(url, headers=hdrs, params=params, timeout=TIMEOUT, verify=False)
        if r.status_code == 200: return r.json()
        log(f"   GET {url.split('/')[-1].split('?')[0]} -> {r.status_code}")
    except Exception as e: log(f"   GET error: {e}")
    return None

def api_post(token, url, body=None):
    hdrs = {"User-Agent":"Mozilla/5.0","Accept":"application/json, text/plain, */*","Content-Type":"application/json","Referer":"https://nepalstock.com.np/"}
    if token: hdrs["Authorization"] = token
    try:
        r = req_lib.post(url, headers=hdrs, json=body or {}, timeout=TIMEOUT, verify=False)
        if r.status_code == 200: return r.json()
        log(f"   POST {url.split('/')[-1].split('?')[0]} -> {r.status_code}")
    except Exception as e: log(f"   POST error: {e}")
    return None

async def get_auth_token():
    log("Launching browser to capture auth token...")
    token_holder = {"token": None}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage","--disable-blink-features=AutomationControlled"])
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36", viewport={"width":1280,"height":900})
        page = await context.new_page()

        async def on_request(request):
            if "api/nots" in request.url and not token_holder["token"]:
                auth = request.headers.get("authorization","")
                if auth and auth.lower().startswith("bearer"):
                    token_holder["token"] = auth
                    log(f"   Token captured: {auth[:40]}...")

        page.on("request", on_request)
        await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,ico}", lambda r: r.abort())

        try:
            log("   Loading nepalstock.com.np/today-price...")
            await page.goto("https://nepalstock.com.np/today-price", wait_until="networkidle", timeout=60000)
            await asyncio.sleep(5)

            if not token_holder["token"]:
                log("   Trying WASM generate_token...")
                wasm_token = await page.evaluate("""
                    () => new Promise((resolve) => {
                        const tryGet = (n) => {
                            if (n <= 0) { resolve(''); return; }
                            if (typeof Module !== 'undefined' && typeof Module.ccall === 'function') {
                                try {
                                    const today = new Date().toISOString().slice(0,10);
                                    const t = Module.ccall('generate_token','string',['string'],[today]);
                                    if (t && t.length > 10) { resolve('Bearer ' + t); return; }
                                    const t2 = Module.ccall('generate_token','string',[],[]);
                                    if (t2 && t2.length > 10) { resolve('Bearer ' + t2); return; }
                                } catch(e) {}
                            }
                            setTimeout(() => tryGet(n-1), 500);
                        };
                        tryGet(30);
                    })
                """)
                if wasm_token: token_holder["token"] = wasm_token; log(f"   WASM token: {wasm_token[:40]}...")

            if not token_holder["token"]:
                log("   Trying market-summary page...")
                await page.goto("https://nepalstock.com.np/market-summary", wait_until="networkidle", timeout=30000)
                await asyncio.sleep(3)

        except Exception as e: log(f"   Browser error: {e}")
        finally: await browser.close()

    log(f"   Token: {'obtained' if token_holder['token'] else 'NOT obtained - will retry with empty token'}")
    return token_holder["token"] or ""

def fetch_nepse_index(token):
    log("Fetching NEPSE index...")
    data = api_get(token, f"{BASE}/nepse-index") or []
    main = next((x for x in data if x.get("index")=="NEPSE"), data[0] if data else {})
    close = str(round(safe_float(main.get("currentValue",0)),2)) if main else "—"
    chg = safe_float(main.get("change",0)); pct = safe_float(main.get("perChange",0))
    s = "+" if chg >= 0 else ""
    chg_str = f"{s}{chg:.2f} ({s}{pct:.2f}%)" if main else "—"
    log(f"   NEPSE: {close}  Chg: {chg_str}")
    return {"nepseClose":close,"nepseChg":chg_str}

def fetch_sub_indices(token):
    log("Fetching sub-indices...")
    data = api_get(token, f"{BASE}/nepse-index") or []
    skip = {"","NEPSE","Float","Sensitive","Sensitive Float"}
    subs = []
    for x in data:
        nm = x.get("index","")
        if nm in skip: continue
        v=round(safe_float(x.get("currentValue",0)),2); c=round(safe_float(x.get("change",0)),2); p=round(safe_float(x.get("perChange",0)),2)
        s="+" if c>=0 else ""
        subs.append({"name":nm,"value":str(v),"chg":f"{s}{c}","chgPct":f"{s}{p}%","direction":"up" if c>=0 else "down"})
    log(f"   Sub-indices: {len(subs)}")
    return subs

def fetch_market_summary(token):
    log("Fetching market summary...")
    d = api_get(token, f"{BASE}/market-summary/") or {}
    return {"turnover":fmt_rs(safe_float(d.get("totalTurnover",0))),"sharesTraded":f"{int(safe_float(d.get('totalTradedShares',0))):,}","transactions":f"{int(safe_float(d.get('totalTransactions',0))):,}","advDecUnch":f"{d.get('advancers','—')} / {d.get('decliners','—')} / {d.get('unchanged','—')}","marketCap":fmt_rs(safe_float(d.get("marketCap",0))),"floatCap":fmt_rs(safe_float(d.get("floatMarketCap",0)))}

def fetch_top_movers(token):
    log("Fetching top movers...")
    gr = api_get(token, f"{BASE}/top-ten/top-gainer?all=false") or []
    lr = api_get(token, f"{BASE}/top-ten/top-loser?all=false") or []
    tr = api_get(token, f"{BASE}/top-ten/turnover?all=false") or []
    vr = api_get(token, f"{BASE}/top-ten/trade?all=false") or []
    gainers  = [{"sym":x.get("symbol",""),"close":str(x.get("ltp","")),"chgPct":f"+{x.get('percentageChange','')}%"} for x in gr[:10] if x.get("symbol")]
    losers   = [{"sym":x.get("symbol",""),"close":str(x.get("ltp","")),"chgPct":f"{x.get('percentageChange','')}%"} for x in lr[:10] if x.get("symbol")]
    turnover = [{"sym":x.get("symbol",""),"ltp":str(x.get("ltp","")),"turnover":fmt_rs(safe_float(x.get("turnover",0)))} for x in tr[:10] if x.get("symbol")]
    volume   = [{"sym":x.get("symbol",""),"shares":str(x.get("totalTradedQuantity","")),"ltp":str(x.get("ltp",""))} for x in vr[:10] if x.get("symbol")]
    log(f"   G:{len(gainers)} L:{len(losers)} T:{len(turnover)} V:{len(volume)}")
    return gainers, losers, turnover, volume

def fetch_broker58(token):
    log(f"Fetching Broker {BROKER_ID} floorsheet...")
    result = {"b58Stance":"—","b58Net":"—","b58Purchase":"—","b58SalesTotal":"—","b58Purchases":[],"b58SalesList":[],"netAccum":[]}
    buy_map = {}; sell_map = {}
    stat = api_get(token, f"{BASE}/securityDailyTradeStat/{BROKER_ID}") or []
    if isinstance(stat, list) and stat:
        log(f"   Got {len(stat)} rows from securityDailyTradeStat")
        for row in stat:
            sym = row.get("symbol","") or row.get("stockSymbol","")
            bq=int(safe_float(row.get("totalPurchaseQuantity",row.get("buyQuantity",0)))); ba=safe_float(row.get("totalPurchaseAmount",row.get("buyAmount",0))); bav=safe_float(row.get("buyAveragePrice",0))
            sq=int(safe_float(row.get("totalSalesQuantity",row.get("sellQuantity",0)))); sa=safe_float(row.get("totalSalesAmount",row.get("sellAmount",0))); sav=safe_float(row.get("sellAveragePrice",0))
            if sym and bq>0: buy_map[sym]={"kitta":bq,"amount":ba,"avg":bav}
            if sym and sq>0: sell_map[sym]={"kitta":sq,"amount":sa,"avg":sav}
    if not buy_map and not sell_map:
        log("   Trying floorsheet endpoint...")
        for ep in [f"{BASE}/security/broker-floorsheet/{BROKER_ID}", f"{BASE}/floorsheet"]:
            fs = api_get(token, ep, {"brokerNumber":BROKER_ID,"size":500,"businessDate":""}) or {}
            sheets = fs.get("floorsheets") or fs.get("content") or (fs if isinstance(fs,list) else [])
            if not sheets: continue
            for row in sheets:
                sym=row.get("stockSymbol","") or row.get("symbol",""); qty=int(safe_float(row.get("contractQuantity",row.get("quantity",0)))); amt=safe_float(row.get("contractAmount",row.get("amount",0))); avg=safe_float(row.get("contractRate",row.get("rate",0)))
                buyer=str(row.get("buyerBrokerCode",row.get("buyerBroker",""))); seller=str(row.get("sellerBrokerCode",row.get("sellerBroker","")))
                if buyer==str(BROKER_ID):
                    if sym not in buy_map: buy_map[sym]={"kitta":0,"amount":0.0,"avg":avg}
                    buy_map[sym]["kitta"]+=qty; buy_map[sym]["amount"]+=amt
                if seller==str(BROKER_ID):
                    if sym not in sell_map: sell_map[sym]={"kitta":0,"amount":0.0,"avg":avg}
                    sell_map[sym]["kitta"]+=qty; sell_map[sym]["amount"]+=amt
            if buy_map or sell_map: break
    bt=sum(v["amount"] for v in buy_map.values()); st=sum(v["amount"] for v in sell_map.values()); net=bt-st; s="+" if net>=0 else ""
    result["b58Purchase"]=fmt_rs(bt); result["b58SalesTotal"]=fmt_rs(st); result["b58Net"]=f"{s}{fmt_rs(abs(net))}"; result["b58Stance"]="NET BUYER" if net>=0 else "NET SELLER"
    result["b58Purchases"]=[{"sym":sym,"mktPct":"—","amount":fmt_rs(v["amount"]),"kitta":f"{v['kitta']:,}","avgPrice":str(round(v["avg"],2)),"txns":"—"} for sym,v in sorted(buy_map.items(),key=lambda x:-x[1]["amount"])[:20]]
    result["b58SalesList"]=[{"sym":sym,"mktPct":"—","amount":fmt_rs(v["amount"]),"kitta":f"{v['kitta']:,}","avgPrice":str(round(v["avg"],2)),"txns":"—"} for sym,v in sorted(sell_map.items(),key=lambda x:-x[1]["amount"])[:20]]
    all_syms=set(list(buy_map)+list(sell_map))
    net_accum=[]
    for sym in all_syms:
        b=buy_map.get(sym,{}).get("kitta",0); s2=sell_map.get(sym,{}).get("kitta",0); nk=b-s2
        net_accum.append({"sym":sym,"netKitta":f"+{nk:,}" if nk>=0 else f"{nk:,}","sellMktPct":"—","convWidth":str(min(100,max(10,abs(nk)//500))),"rating":"★★★" if abs(nk)>50000 else "★★" if abs(nk)>10000 else "★","note":f"B58 {'accumulating' if nk>=0 else 'distributing'} {abs(nk):,} net kitta"})
    net_accum.sort(key=lambda x:int(x["netKitta"].replace("+","").replace(",","")),reverse=True)
    result["netAccum"]=net_accum
    log(f"   Buy:{result['b58Purchase']} Sell:{result['b58SalesTotal']} Net:{result['b58Net']}  P:{len(result['b58Purchases'])} S:{len(result['b58SalesList'])}")
    return result

def fetch_technicals(token, watchlist):
    log(f"Fetching technicals for {len(watchlist)} stocks...")
    data = api_post(token, f"{BASE}/nepse-data/today-price?", {"id":58,"size":500,"page":0,"sortBy":"","sortAsc":True,"sector":"","isNonDelisted":True,"businessDate":""})
    price_map = {}
    if data:
        rows = data.get("content", data if isinstance(data,list) else [])
        price_map = {r.get("symbol",""):r for r in rows}
    log(f"   Price map: {len(price_map)} stocks")
    technical = []
    for sym in watchlist:
        s=price_map.get(sym,{}); ltp=str(s.get("closingPrice","—")); w52h=str(s.get("fiftyTwoWeekHigh","—")); w52l=str(s.get("fiftyTwoWeekLow","—"))
        chg=s.get("percentageChange","—"); chg_s=(f"+{chg:.2f}%" if isinstance(chg,(int,float)) and chg>=0 else f"{chg:.2f}%" if isinstance(chg,(int,float)) else "—")
        technical.append({"sym":sym,"ltp":ltp,"w52h":w52h,"w52l":w52l,"chg":chg_s,"rsi":"—","adx":"—","atr":"—","aroon":"—","adOsc":"—","signal":"Neutral","action":"WATCH"})
    return technical

def build_trade_plan(technical, net_accum):
    accum_map={n["sym"]:n["netKitta"] for n in net_accum}
    adds=sorted([t for t in technical if "ADD" in t.get("action","").upper()],key=lambda t:safe_float(t.get("adx","0")),reverse=True)
    plan=[]
    for i,t in enumerate(adds[:15],1):
        ltp=safe_float(t["ltp"]); atr=safe_float(t["atr"])
        if ltp<=0: continue
        stop=round(ltp-1.5*atr,2) if atr>0 else round(ltp*0.92,2); t1,t2,t3=round(ltp*1.12,2),round(ltp*1.20,2),round(ltp*1.30,2); risk=ltp-stop; reward=t1-ltp; rr=f"1:{round(reward/risk,1)}" if risk>0 else "1:2.0"
        nk=accum_map.get(t["sym"],"—")
        plan.append({"rk":str(i),"sym":t["sym"],"ltp":t["ltp"],"w52hl":f"{t['w52h']}/{t['w52l']}","entry":f"{round(ltp*0.99,2)}-{round(ltp*1.01,2)}","stop":str(stop),"t1":str(t1),"t2":str(t2),"t3":str(t3),"rr":rr,"action":f"ADD — B58 {nk}" if nk!="—" else "ADD"})
    return plan

def build_action_plan(technical, net_accum):
    accum_map={n["sym"]:n for n in net_accum}; order={"URGENT":0,"MONITOR":1,"WATCH":2,"AVOID":3}; plan=[]
    for t in technical:
        action=t.get("action","WATCH").upper(); sym=t["sym"]; nk=(accum_map.get(sym) or {}).get("netKitta","—")
        if "ADD" in action or "BUY" in action: pri,pt,note="URGENT","urgent",f"B58 {nk}. ADD." if nk!="—" else "ADD."
        elif "HOLD" in action: pri,pt,note="MONITOR","monitor",f"Hold."
        elif "AVOID" in action: pri,pt,note="AVOID","avoid-row","Overbought/bearish."
        else: pri,pt,note="WATCH","watch","Watch for entry."
        plan.append({"priority":pri,"sym":sym,"ltp":t["ltp"],"w52h":t["w52h"],"action":action,"note":note,"type":pt})
    plan.sort(key=lambda x:order.get(x["priority"],99)); return plan

def build_key_insights(nepse_data, b58_data, technical):
    ins=[]; stance=b58_data.get("b58Stance","—"); net=b58_data.get("b58Net","—"); top_buy=b58_data["b58Purchases"][0]["sym"] if b58_data.get("b58Purchases") else "—"
    ins.append({"num":"1","title":f"B58 is a {stance} — {net}","body":f"Broker 58 net {net}. Top buy: {top_buy}. {'Accumulation signals confidence.' if 'BUYER' in stance else 'Distribution — caution.'}"})
    chg=nepse_data.get("nepseChg",""); adv=nepse_data.get("advDecUnch","—")
    ins.append({"num":"2","title":f"NEPSE {'rallied' if '+' in chg else 'declined'} {chg}","body":f"A/D/U: {adv}. Turnover: {nepse_data.get('turnover','—')}."})
    return ins

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().strftime("%Y-%m-%d"))
    parser.add_argument("--no-alpha", action="store_true")
    parser.add_argument("--stocks", default="")
    args = parser.parse_args()
    report_date=args.date.strip()
    watchlist=[s.strip().upper() for s in args.stocks.split(",")] if args.stocks else WATCHLIST
    log(f"=== NEPSE Extractor v3 — {report_date} ===")
    token = await get_auth_token()
    idx=fetch_nepse_index(token); summary=fetch_market_summary(token); subs=fetch_sub_indices(token)
    gainers,losers,turnover,volume=fetch_top_movers(token); b58=fetch_broker58(token)
    tech=[] if args.no_alpha else fetch_technicals(token, watchlist)
    trade_plan=build_trade_plan(tech,b58.get("netAccum",[])); action_plan=build_action_plan(tech,b58.get("netAccum",[])); insights=build_key_insights({**idx,**summary},b58,tech)
    chg=idx.get("nepseChg",""); stance=b58.get("b58Stance","—")
    headline=("STRONG GREEN / B58 Accumulating" if "+" in chg and "BUYER" in stance else "GREEN / Cautious Rally" if "+" in chg else "MIXED / B58 Buying on Dip" if stance=="NET BUYER" else "RED / Distribution Pressure")
    b58p=b58.get("b58Purchases",[])
    report={"date":report_date,"headline":headline,"nepseClose":idx.get("nepseClose","—"),"nepseChg":idx.get("nepseChg","—"),"turnover":summary.get("turnover","—"),"sharesTraded":summary.get("sharesTraded","—"),"transactions":summary.get("transactions","—"),"advDecUnch":summary.get("advDecUnch","—"),"marketCap":summary.get("marketCap","—"),"floatCap":summary.get("floatCap","—"),"b58Stance":b58.get("b58Stance","—"),"b58Net":b58.get("b58Net","—"),"b58Purchase":b58.get("b58Purchase","—"),"b58SalesTotal":b58.get("b58SalesTotal","—"),"b58TopBuy":b58p[0]["sym"] if b58p else "—","b58PeakMkt":b58p[0].get("mktPct","—") if b58p else "—","marketPulseNote":f"NEPSE {idx.get('nepseClose','—')} ({idx.get('nepseChg','—')}) turnover {summary.get('turnover','—')}. B58 {b58.get('b58Stance','—')} {b58.get('b58Net','—')}.","subIndices":subs,"topGainers":gainers,"topLosers":losers,"topTurnover":turnover,"topVolume":volume,"b58Purchases":b58.get("b58Purchases",[]),"b58SalesList":b58.get("b58SalesList",[]),"netAccum":b58.get("netAccum",[]),"technical":tech,"tradePlan":trade_plan,"keyInsights":insights,"actionPlan":action_plan,"disclaimer":["Not financial advice — personal tracking only.","Data: nepalstock.com.np",f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} NPT"]}
    out=Path(OUTPUT_DIR)/f"{report_date}.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    with open(out,"w",encoding="utf-8") as f: json.dump(report,f,ensure_ascii=False,indent=2)
    log(f"Saved: {out}  NEPSE:{report['nepseClose']}  B58:{report['b58Stance']} {report['b58Net']}  Stocks:{len(tech)}")
    log("=== Done ===")

if __name__ == "__main__":
    asyncio.run(main())
