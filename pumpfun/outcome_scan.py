"""One-shot outcome discovery for captured Pump.fun launches.
Reads the GitHub Actions artifact JSONL, never submits trades.
Only post-graduation DEX pool OHLCV can be measured from GeckoTerminal.
"""
import csv, json, os, time, collections
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
import requests

DATA=Path("pumpfun/outcomes")
DATA.mkdir(parents=True,exist_ok=True)
SESSION=requests.Session()
SESSION.headers.update({"User-Agent":"pumpfun-readonly-outcomes/1.0"})
base="https://api.geckoterminal.com/api/v2"
def get(url, retries=3):
    for attempt in range(retries):
        try:
            r=SESSION.get(url,timeout=22)
            if r.status_code==429:
                time.sleep(10*(attempt+1))
                continue
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            if attempt==retries-1:return {"_error":str(exc)[:250]}
            time.sleep(2*(attempt+1))
    return {"_error":"rate limited"}

records=[]
for line in Path("captured/pumpfun-launches.jsonl").read_text().splitlines():
    try:
        j=json.loads(line)
        if j.get("mint"): records.append(j)
    except ValueError:pass
unique={r["mint"]:r for r in records}
records=list(unique.values())
counts=collections.Counter(r.get("creator") for r in records)
print("Launches:",len(records))
pairs={}
dex_errors=[]
mints=list(unique)
for i in range(0,len(mints),25):
    chunk=mints[i:i+25]
    result=get("https://api.dexscreener.com/latest/dex/tokens/"+",".join(chunk))
    if "_error" in result:dex_errors.append(result["_error"])
    for pair in result.get("pairs") or []:
        mint=(pair.get("baseToken") or {}).get("address")
        if mint not in unique or pair.get("chainId")!="solana":continue
        pairs.setdefault(mint,[]).append(pair)
    time.sleep(1)
print("Tokens appearing on DEX:",len(pairs))
rows=[]
for r in records:
    arr=pairs.get(r["mint"],[])
    best=max(arr,key=lambda p:float((p.get("liquidity") or {}).get("usd") or 0),default=None)
    market=best or {}
    liquidity=float((market.get("liquidity") or {}).get("usd") or 0)
    launch_time=datetime.fromisoformat(r["received_at"].replace("Z","+00:00")).timestamp()
    created=(market.get("pairCreatedAt") or 0)/1000
    row={"mint":r["mint"],"symbol":r.get("symbol",""),"name":r.get("name",""),
         "creator":r.get("creator",""),"creator_launches_in_sample":counts[r.get("creator")],
         "initial_buy":r.get("initial_buy"),"initial_mcap_sol":r.get("market_cap_sol"),
         "found_dex_pair":bool(best),"dex_liquidity_usd":liquidity,
         "dex_price_now_usd":market.get("priceUsd"),"dex_pair_address":market.get("pairAddress"),
         "dex_name":market.get("dexId"),"dex_pair_created_at":created or None,
         "launch_to_dex_minutes":round((created-launch_time)/60,1) if created else None,
         "post_dex_3h_peak_multiple":None,"post_dex_3h_end_multiple":None,"history_status":"not_checked"}
    rows.append(row)
# Restrict to 12 historical queries: GeckoTerminal public API is ~10 requests/min.
eligible=[row for row in rows if row["found_dex_pair"] and row["dex_pair_address"]]
eligible.sort(key=lambda x:x["dex_liquidity_usd"],reverse=True)
for idx,row in enumerate(eligible[:12]):
    created=int(row["dex_pair_created_at"] or 0)
    if not created: row["history_status"]="missing_pool_time";continue
    # Only candles from first three hours of DEX pool life, not bonding-curve period.
    endpoint=(f"{base}/networks/solana/pools/{quote(row['dex_pair_address'])}/ohlcv/minute"
              f"?aggregate=1&limit=200&before_timestamp={created+3*3600}&currency=usd&token={quote(row['mint'])}")
    result=get(endpoint)
    candles=((result.get("data") or {}).get("attributes") or {}).get("ohlcv_list") or []
    candles=sorted(c for c in candles if created<=c[0]<=created+3*3600)
    if candles and candles[0][1] and float(candles[0][1])>0:
        entry=float(candles[0][1])
        row["post_dex_3h_peak_multiple"]=round(max(float(c[2]) for c in candles)/entry,3)
        row["post_dex_3h_end_multiple"]=round(float(candles[-1][4])/entry,3)
        row["history_status"]="pool_ohlcv_only"
    else:row["history_status"]=str(result.get("_error") or "no_pool_candles")[:90]
    time.sleep(7)
for row in eligible[12:]:row["history_status"]="api_rate_cap_not_checked"
with (DATA/"token_outcomes.csv").open("w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
report={"sample_launches":len(rows),"dex_pairs_found":len(eligible),
        "dex_history_checked":sum(x["history_status"]=="pool_ohlcv_only" for x in rows),
        "dex_errors":dex_errors,
        "tokens_from_creators_with_3plus_launches":sum(x["creator_launches_in_sample"]>=3 for x in rows),
        "post_dex_peak_2x":sum((x["post_dex_3h_peak_multiple"] or 0)>=2 for x in rows),
        "post_dex_peak_5x":sum((x["post_dex_3h_peak_multiple"] or 0)>=5 for x in rows),
        "post_dex_peak_10x":sum((x["post_dex_3h_peak_multiple"] or 0)>=10 for x in rows),
        "caveats":["Only DEX pools: pre-graduation bonding-curve pumps are NOT measured.",
        "Unlisted tokens and missing history have UNKNOWN returns, not zero.",
        "OHLCV highs are not guaranteed executable sell prices.",
        "Peak rates cannot establish 50-euro trading P&L or stop order fills.",
        "Top 12 by present liquidity creates survivorship bias; never interpret as token-wide hit rate."]}
(DATA/"summary.json").write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
