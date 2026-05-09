"""
NEPSE Daily Data Extractor
===========================
Scrapes nepalstock.com.np and nepse-alpha.com after market close
and produces a YYYY-MM-DD.json ready to upload to your GitHub repo.

Requirements:
    pip install playwright
    playwright install chromium

Usage:
    python nepse_scraper.py                  # scrapes today's data
    python nepse_scraper.py --date 2026-05-09  # scrapes a specific date
    python nepse_scraper.py --stocks NHPC,NABIL,NICA  # only these stocks on Alpha
    python nepse_scraper.py --upload          # auto-upload to GitHub (needs token)

Config:
    Edit the CONFIG section below before running.
"""

import asyncio
import json
import re
import sys
import os
import argparse
from datetime import datetime, date
from pathlib import Path

try:
    import requests as req_lib
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

CONFIG = {
    "broker_id": "58",
    "watchlist": [
        "NHPC", "NABIL", "NICA", "NIFRA", "GBIME",
        "SHIVM", "LBBL", "NRN", "AKJCL", "UPPER",
        "HIDCL", "SWBBL", "CHCL", "SRBL", "CZBIL",
        "SANIMA", "PRVU", "NBL", "RLFL", "NLBBL",
    ],
    "output_dir": ".",
    "github_token": "",
    "github_user": "SagunPrajapati",
    "github_repo": "share",
    "github_branch": "main",
    "headless": True,
    "slow_mo": 0,
    "timeout": 30000,
}

def clean_num(s):
    return str(s or "").replace(",", "").strip()

def safe_float(s):
    try:
        return float(clean_num(str(s)).replace("Rs.", "").replace("%", "").strip())
    except:
        return 0.0

def fmt_rs(val):
    if val >= 1_000_000_000:
        return f"Rs.{val/1_000_000_000:.2f}B"
    if val >= 1_000_000:
        return f"Rs.{val/1_000_000:.2f}M"
    return f"Rs.{val:,.0f}"

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

async def scrape_nepse(page, report_date):
    log("Scraping NEPSE main index...")
    data = {}
    try:
        await page.goto("https://nepalstock.com.np/", timeout=CONFIG["timeout"])
        await page.wait_for_load_state("networkidle", timeout=CONFIG["timeout"])
        await asyncio.sleep(2)
        try:
            nepse_val = await page.locator("text=/\\d{4,5}\\.\\d{2}/").first.text_content(timeout=5000)
            data["nepseClose"] = nepse_val.strip()
        except:
            data["nepseClose"] = "—"
        try:
            chg_el = await page.locator(".nepse-change, .index-change, [class*='change']").first.text_content(timeout=5000)
            data["nepseChg"] = chg_el.strip()
        except:
            data["nepseChg"] = "—"
        log(f"   NEPSE Close: {data['nepseClose']}  Chg: {data['nepseChg']}")
    except Exception as e:
        log(f"   NEPSE index error: {e}")

    log("Scraping market summary...")
    try:
        await page.goto("https://nepalstock.com.np/market-summary", timeout=CONFIG["timeout"])
        await page.wait_for_load_state("networkidle", timeout=CONFIG["timeout"])
        await asyncio.sleep(2)
        rows = await page.locator("table tr, .summary-row, .market-stat").all()
        summary_text = ""
        for row in rows:
            txt = await row.text_content()
            summary_text += txt + "\n"
        to_match = re.search(r"Total Turnover.*?Rs\.?\s*([\d,]+\.?\d*)", summary_text, re.IGNORECASE)
        if to_match:
            data["turnover"] = fmt_rs(safe_float(to_match.group(1)))
        sh_match = re.search(r"Total Traded Shares.*?([\d,]+)", summary_text, re.IGNORECASE)
        if sh_match:
            data["sharesTraded"] = sh_match.group(1).strip()
        tx_match = re.search(r"Total Transactions.*?([\d,]+)", summary_text, re.IGNORECASE)
        if tx_match:
            data["transactions"] = tx_match.group(1).strip()
        adv_match = re.search(r"Advance.*?(\d+).*?Decline.*?(\d+).*?Unchanged.*?(\d+)", summary_text, re.IGNORECASE | re.DOTALL)
        if adv_match:
            data["advDecUnch"] = f"{adv_match.group(1)} / {adv_match.group(2)} / {adv_match.group(3)}"
    except Exception as e:
        log(f"   Market summary error: {e}")

    log("Scraping sub-indices...")
    sub_indices = []
    try:
        await page.goto("https://nepalstock.com.np/indices", timeout=CONFIG["timeout"])
        await page.wait_for_load_state("networkidle", timeout=CONFIG["timeout"])
        await asyncio.sleep(2)
        rows = await page.locator("table tbody tr").all()
        for row in rows:
            cells = await row.locator("td").all()
            if len(cells) >= 3:
                texts = [await c.text_content() for c in cells]
                name = texts[0].strip()
                value = texts[1].strip().replace(",", "")
                chg_raw = texts[2].strip() if len(texts) > 2 else "0"
                chg_pct = texts[3].strip() if len(texts) > 3 else "0%"
                direction = "up" if not chg_raw.startswith("-") else "down"
                if name and value:
                    sub_indices.append({"name": name, "value": value, "chg": chg_raw, "chgPct": chg_pct if "%" in chg_pct else chg_pct + "%", "direction": direction})
        log(f"   Sub-indices: {len(sub_indices)}")
    except Exception as e:
        log(f"   Sub-indices error: {e}")
    data["subIndices"] = sub_indices

    log("Scraping top movers...")
    data["topGainers"] = []; data["topLosers"] = []; data["topTurnover"] = []; data["topVolume"] = []
    try:
        await page.goto("https://nepalstock.com.np/today-price", timeout=CONFIG["timeout"])
        await page.wait_for_load_state("networkidle", timeout=CONFIG["timeout"])
        await asyncio.sleep(3)
        for tab_text, key in [("Gainer", "topGainers"), ("Loser", "topLosers"), ("Turnover", "topTurnover")]:
            try:
                await page.locator(f"button:has-text('{tab_text}'), text={tab_text}").first.click(timeout=3000)
                await asyncio.sleep(1)
                rows = await page.locator("table tbody tr").all()
                for row in rows[:10]:
                    cells = [await c.text_content() for c in await row.locator("td").all()]
                    if len(cells) >= 3:
                        data[key].append({"sym": cells[0].strip(), "close": cells[1].strip().replace(",", ""), "chgPct": cells[-1].strip()})
            except:
                pass
        log(f"   Gainers:{len(data['topGainers'])} Losers:{len(data['topLosers'])} Turnover:{len(data['topTurnover'])}")
    except Exception as e:
        log(f"   Movers error: {e}")
    return data

async def scrape_broker58(page, broker_id):
    log(f"Scraping Broker {broker_id} floorsheet...")
    result = {"b58Stance": "—", "b58Net": "—", "b58Purchase": "—", "b58SalesTotal": "—", "b58Purchases": [], "b58SalesList": [], "netAccum": []}
    try:
        await page.goto(f"https://nepalstock.com.np/broker-detail#{broker_id}", timeout=CONFIG["timeout"])
        await page.wait_for_load_state("networkidle", timeout=CONFIG["timeout"])
        await asyncio.sleep(3)
        try:
            await page.locator(f"text={broker_id}").first.click(timeout=3000)
            await asyncio.sleep(2)
        except:
            pass
        buy_total = 0.0; sell_total = 0.0; buy_data = {}; sell_data = {}
        tables = await page.locator("table").all()
        for table in tables:
            header_text = await table.locator("thead").text_content() if await table.locator("thead").count() > 0 else ""
            is_buy = "buy" in header_text.lower() or "purchase" in header_text.lower()
            is_sell = "sell" in header_text.lower() or "sale" in header_text.lower()
            if is_buy or is_sell:
                rows = await table.locator("tbody tr").all()
                for row in rows:
                    cells = [await c.text_content() for c in await row.locator("td").all()]
                    if len(cells) >= 4:
                        sym = cells[0].strip()
                        kitta = int(cells[1].strip().replace(",","")) if cells[1].strip().replace(",","").isdigit() else 0
                        amt = safe_float(cells[2].strip().replace(",","").replace("Rs.",""))
                        avg_raw = cells[3].strip().replace(",","")
                        mkt_pct = cells[4].strip() if len(cells) > 4 else "—"
                        txns = cells[5].strip() if len(cells) > 5 else "—"
                        if is_buy:
                            buy_total += amt; buy_data[sym] = kitta
                            result["b58Purchases"].append({"sym": sym, "mktPct": mkt_pct, "amount": fmt_rs(amt), "kitta": f"{kitta:,}", "avgPrice": avg_raw, "txns": txns})
                        else:
                            sell_total += amt; sell_data[sym] = kitta
                            result["b58SalesList"].append({"sym": sym, "mktPct": mkt_pct, "amount": fmt_rs(amt), "kitta": f"{kitta:,}", "avgPrice": avg_raw, "txns": txns})
        net = buy_total - sell_total
        result["b58Purchase"] = fmt_rs(buy_total); result["b58SalesTotal"] = fmt_rs(sell_total)
        result["b58Net"] = f"+{fmt_rs(net)}" if net >= 0 else fmt_rs(net).replace("Rs.", "-Rs.")
        result["b58Stance"] = "NET BUYER" if net >= 0 else "NET SELLER"
        all_syms = set(list(buy_data.keys()) + list(sell_data.keys()))
        net_accum = []
        for sym in all_syms:
            b = buy_data.get(sym, 0); s = sell_data.get(sym, 0); net_k = b - s
            conviction = min(100, max(10, abs(net_k) // 1000))
            rating = "★★★" if abs(net_k) > 50000 else "★★" if abs(net_k) > 10000 else "★"
            net_accum.append({"sym": sym, "netKitta": f"+{net_k:,}" if net_k >= 0 else f"{net_k:,}", "sellMktPct": next((x["mktPct"] for x in result["b58SalesList"] if x["sym"] == sym), "—"), "convWidth": str(conviction), "rating": rating, "note": f"B58 {'accumulating' if net_k >= 0 else 'distributing'} {abs(net_k):,} net kitta"})
        net_accum.sort(key=lambda x: int(x["netKitta"].replace("+","").replace(",","")), reverse=True)
        result["netAccum"] = net_accum
        log(f"   Buy:{result['b58Purchase']} Sell:{result['b58SalesTotal']} Net:{result['b58Net']}")
    except Exception as e:
        log(f"   Broker error: {e}")
    return result

async def scrape_nepse_alpha(page, watchlist):
    log(f"Scraping NEPSE Alpha for {len(watchlist)} stocks...")
    technical = []
    for sym in watchlist:
        log(f"   -> {sym}")
        try:
            await page.goto(f"https://nepse-alpha.com/company/{sym.lower()}", timeout=CONFIG["timeout"])
            await page.wait_for_load_state("networkidle", timeout=CONFIG["timeout"])
            await asyncio.sleep(1.5)
            content = await page.content()
            ltp = "—"
            try:
                ltp_el = await page.locator("[class*='ltp'], [class*='price'], [class*='current-price']").first.text_content(timeout=3000)
                ltp = ltp_el.strip().replace(",","")
            except:
                m = re.search(r'"ltp":\s*"?([\d.]+)"?', content)
                if m: ltp = m.group(1)
            w52h, w52l, rsi, adx, atr, aroon, ad_osc = "—","—","—","—","—","—","—"
            for pattern, var in [(r'RSI[^0-9]*(\d{1,2}\.\d{1,2})', 'rsi'),(r'ADX[^0-9]*(\d{1,2}\.\d{1,2})', 'adx'),(r'ATR[^0-9]*([\d]+\.[\d]+)', 'atr'),(r'Aroon[^0-9]*(\d{1,3}\.?\d*)', 'aroon')]:
                m = re.search(pattern, content, re.IGNORECASE)
                if m: exec(f"{var} = m.group(1)")
            if aroon != "—" and "%" not in aroon: aroon += "%"
            ad_m = re.search(r'[Aa]ccumulation.*?(Bullish|Bearish|Neutral)', content)
            if ad_m: ad_osc = ad_m.group(1)
            rsi_f = safe_float(rsi); adx_f = safe_float(adx)
            signal = "Neutral"; action = "WATCH"
            if rsi_f > 70: signal, action = "Overbought", "AVOID"
            elif rsi_f > 55 and adx_f > 25: signal, action = "Bullish", "ADD"
            elif rsi_f > 50: signal, action = "Mild Bullish", "HOLD"
            elif rsi_f < 30: signal, action = "Oversold", "WATCH"
            elif rsi_f < 45 and adx_f > 25: signal, action = "Bearish", "AVOID"
            technical.append({"sym": sym, "ltp": ltp, "w52h": w52h, "w52l": w52l, "chg": "—", "rsi": rsi, "adx": adx, "atr": atr, "aroon": aroon, "adOsc": ad_osc, "signal": signal, "action": action})
        except Exception as e:
            log(f"   {sym} error: {e}")
            technical.append({"sym": sym, "ltp": "—", "w52h": "—", "w52l": "—", "chg": "—", "rsi": "—", "adx": "—", "atr": "—", "aroon": "—", "adOsc": "—", "signal": "—", "action": "WATCH"})
    return technical

def build_trade_plan(technical, net_accum):
    trade_plan = []; accum_map = {n["sym"]: n["netKitta"] for n in net_accum}
    add_stocks = sorted([t for t in technical if "ADD" in t.get("action","").upper()], key=lambda t: safe_float(t.get("adx","0")), reverse=True)
    for i, t in enumerate(add_stocks[:15], 1):
        ltp = safe_float(t["ltp"]); atr = safe_float(t["atr"])
        if ltp <= 0: continue
        stop = round(ltp - (1.5 * atr), 2) if atr > 0 else round(ltp * 0.92, 2)
        t1 = round(ltp * 1.12, 2); t2 = round(ltp * 1.20, 2); t3 = round(ltp * 1.30, 2)
        risk = ltp - stop; reward = t1 - ltp
        rr = f"1:{round(reward/risk,1)}" if risk > 0 else "1:2.0"
        net_k = accum_map.get(t["sym"], "—")
        trade_plan.append({"rk": str(i), "sym": t["sym"], "ltp": t["ltp"], "w52hl": f"{t['w52h']}/{t['w52l']}", "entry": f"{round(ltp*0.99,2)}-{round(ltp*1.01,2)}", "stop": str(stop), "t1": str(t1), "t2": str(t2), "t3": str(t3), "rr": rr, "action": f"ADD — B58 {net_k}" if net_k != "—" else "ADD — Technical signal"})
    return trade_plan

def build_action_plan(technical, net_accum):
    action_plan = []; accum_map = {n["sym"]: n for n in net_accum}
    order = {"URGENT": 0, "MONITOR": 1, "WATCH": 2, "AVOID": 3}
    for t in technical:
        action = t.get("action","WATCH").upper(); sym = t["sym"]; net_k = (accum_map.get(sym) or {}).get("netKitta","—")
        if "ADD" in action or "BUY" in action: priority, plan_type, note = "URGENT", "urgent", f"B58 {net_k}. ADD on pullback." if net_k != "—" else "Strong technical signal. ADD."
        elif "HOLD" in action: priority, plan_type, note = "MONITOR", "monitor", f"Hold position. RSI {t.get('rsi','—')}."
        elif "AVOID" in action: priority, plan_type, note = "AVOID", "avoid-row", f"RSI {t.get('rsi','—')} — overbought/bearish."
        else: priority, plan_type, note = "WATCH", "watch", f"Watch for entry. ADX {t.get('adx','—')}."
        action_plan.append({"priority": priority, "sym": sym, "ltp": t["ltp"], "w52h": t["w52h"], "action": action, "note": note, "type": plan_type})
    action_plan.sort(key=lambda x: order.get(x["priority"], 99))
    return action_plan

def build_key_insights(nepse_data, b58_data, technical):
    insights = []
    stance = b58_data.get("b58Stance","—"); net = b58_data.get("b58Net","—")
    top_buy = b58_data["b58Purchases"][0]["sym"] if b58_data.get("b58Purchases") else "—"
    insights.append({"num":"1","title":f"B58 is a {stance} — {net}","body":f"Broker 58 recorded net {net}. Top buy: {top_buy}. {'Accumulation signals confidence.' if 'BUYER' in stance else 'Distribution pressure — caution.'}"})
    chg = nepse_data.get("nepseChg",""); adv_dec = nepse_data.get("advDecUnch","—")
    insights.append({"num":"2","title":f"NEPSE {'rallied' if '+' in chg else 'declined'} {chg}","body":f"Advance/Decline/Unchanged: {adv_dec}. Turnover: {nepse_data.get('turnover','—')}."})
    strong = [t for t in technical if safe_float(t.get("rsi","0")) > 55 and safe_float(t.get("adx","0")) > 25]
    if strong: insights.append({"num":"3","title":f"Strong Technical Confluence: {', '.join(t['sym'] for t in strong[:5])}","body":f"RSI>55 and ADX>25 — trending momentum. Scale in on pullbacks."})
    ob = [t for t in technical if safe_float(t.get("rsi","0")) > 70]
    if ob: insights.append({"num":"4","title":f"Overbought Warning: {', '.join(t['sym'] for t in ob[:3])}","body":"RSI above 70 — avoid chasing. Wait for RSI to cool below 65."})
    return insights

async def main():
    parser = argparse.ArgumentParser(description="NEPSE Daily Data Extractor")
    parser.add_argument("--date", default=date.today().strftime("%Y-%m-%d"))
    parser.add_argument("--stocks", default="")
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--no-alpha", action="store_true")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    report_date = args.date
    watchlist = [s.strip().upper() for s in args.stocks.split(",")] if args.stocks else CONFIG["watchlist"]
    if args.headed: CONFIG["headless"] = False
    log(f"=== NEPSE Extractor — {report_date} ===")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=CONFIG["headless"], slow_mo=CONFIG["slow_mo"], args=["--no-sandbox","--disable-dev-shm-usage"])
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36", viewport={"width":1280,"height":900}, locale="en-US")
        page = await context.new_page()
        await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf}", lambda r: r.abort())
        nepse_data = await scrape_nepse(page, report_date)
        b58_data = await scrape_broker58(page, CONFIG["broker_id"])
        technical = [] if args.no_alpha else await scrape_nepse_alpha(page, watchlist)
        await browser.close()
    trade_plan = build_trade_plan(technical, b58_data.get("netAccum",[]))
    action_plan = build_action_plan(technical, b58_data.get("netAccum",[]))
    key_insights = build_key_insights(nepse_data, b58_data, technical)
    nepse_chg = nepse_data.get("nepseChg",""); b58_stance = b58_data.get("b58Stance","—")
    headline = "STRONG GREEN / B58 Accumulating" if "+" in nepse_chg and "BUYER" in b58_stance else "GREEN / Cautious Rally" if "+" in nepse_chg else "MIXED / B58 Buying on Dip" if b58_stance == "NET BUYER" else "RED / Distribution Pressure"
    report = {"date":report_date,"headline":headline,"nepseClose":nepse_data.get("nepseClose","—"),"nepseChg":nepse_data.get("nepseChg","—"),"turnover":nepse_data.get("turnover","—"),"sharesTraded":nepse_data.get("sharesTraded","—"),"transactions":nepse_data.get("transactions","—"),"advDecUnch":nepse_data.get("advDecUnch","—"),"marketCap":nepse_data.get("marketCap","—"),"floatCap":nepse_data.get("floatCap","—"),"b58Stance":b58_data.get("b58Stance","—"),"b58Net":b58_data.get("b58Net","—"),"b58Purchase":b58_data.get("b58Purchase","—"),"b58SalesTotal":b58_data.get("b58SalesTotal","—"),"b58TopBuy":b58_data["b58Purchases"][0]["sym"] if b58_data.get("b58Purchases") else "—","b58PeakMkt":b58_data["b58Purchases"][0]["mktPct"] if b58_data.get("b58Purchases") else "—","marketPulseNote":f"NEPSE closed at {nepse_data.get('nepseClose','—')} ({nepse_data.get('nepseChg','—')}) with turnover of {nepse_data.get('turnover','—')}. Broker 58 was a {b58_data.get('b58Stance','—')} with net {b58_data.get('b58Net','—')}.","subIndices":nepse_data.get("subIndices",[]),"topGainers":nepse_data.get("topGainers",[]),"topLosers":nepse_data.get("topLosers",[]),"topTurnover":nepse_data.get("topTurnover",[]),"topVolume":nepse_data.get("topVolume",[]),"b58Purchases":b58_data.get("b58Purchases",[]),"b58SalesList":b58_data.get("b58SalesList",[]),"netAccum":b58_data.get("netAccum",[]),"technical":technical,"tradePlan":trade_plan,"keyInsights":key_insights,"actionPlan":action_plan,"disclaimer":["Not financial advice — Personal tracking only.","Data sourced from nepalstock.com.np and nepse-alpha.com.","Always do your own research before investing.",f"Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} NPT"]}
    out_path = Path(CONFIG["output_dir"]) / f"{report_date}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path,"w",encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    log(f"Saved: {out_path} — NEPSE:{report['nepseClose']} B58:{report['b58Stance']} {report['b58Net']}")
    if args.upload and HAS_REQUESTS and CONFIG["github_token"]:
        import base64
        url = f"https://api.github.com/repos/{CONFIG['github_user']}/{CONFIG['github_repo']}/contents/{report_date}.json"
        headers = {"Authorization": f"token {CONFIG['github_token']}", "Accept": "application/vnd.github.v3+json"}
        existing = req_lib.get(url, headers=headers)
        sha = existing.json().get("sha") if existing.status_code == 200 else None
        payload = {"message": f"Auto: Add report {report_date}", "content": base64.b64encode(open(out_path,"rb").read()).decode(), "branch": CONFIG["github_branch"]}
        if sha: payload["sha"] = sha
        resp = req_lib.put(url, headers=headers, json=payload)
        log(f"Upload: {'OK' if resp.status_code in (200,201) else 'FAILED'} ({resp.status_code})")
    log("=== Done ===")

if __name__ == "__main__":
    asyncio.run(main())
