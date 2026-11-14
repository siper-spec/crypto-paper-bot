"""Migration-to-five-minute PROXY only, not actual BOOST start/end.
Stream a historical hour and use actual PumpSwap trade prices on migrated mints.
"""
import json,collections,io,requests,zstandard,os,statistics,csv
from pathlib import Path
P=Path("pumpfun/boost_backtest_results");P.mkdir(parents=True,exist_ok=True)
report={"strategy":"first PumpSwap price after migration -> first trade at/after 5min",
"exact_boost_events":False,"unfunded":True,"source":"Shrine historical archive",
"sample":{},"pairs":[],"limitations":["NOT an exact BOOST backtest: explicit start/end BOOST transactions are unavailable in this archive",
"Quoted trade prices are not executable fills","Migrations with incomplete observations excluded","Single-hour sample, biased and not statistically reliable"]}
try:
 idx=requests.get("https://replay.shrine.trade/pump/index.json",timeout=20);idx.raise_for_status()
 hs=idx.json()["hours"]
 hour=hs[-5];report["hour_utc"]=hour;sample={}
 url="https://replay.shrine.trade/pump/"+hour+".jsonl.zst"
 count=0
 with requests.get(url,stream=True,timeout=45) as r:
  r.raise_for_status()
  reader=zstandard.ZstdDecompressor().stream_reader(r.raw)
  for line in io.TextIOWrapper(reader,encoding="utf8"):
   count+=1
   if count>3000000:break
   try:e=json.loads(line)
   except ValueError:continue
   mint=e.get("mint");t=e.get("timestamp")
   if not mint or not isinstance(t,(int,float)):continue
   a=e.get("action")
   if a=="migrate" and e.get("protocol")=="PUMPFUN":
    sample.setdefault(mint,dict(mint=mint,start=t,entry=None,exit=None,trades=0))
   elif mint in sample and e.get("protocol")=="PUMPSWAP" and a in ("buy","sell"):
    z=sample[mint];p=e.get("price")
    try:p=float(p)
    except (TypeError,ValueError):continue
    if p<=0 or t<z["start"]:continue
    z["trades"]+=1
    if z["entry"] is None:z["entry"]=(t,p,e.get("quoteMint"))
    elif z["exit"] is None and t>=z["start"]+300:z["exit"]=(t,p)
 report["sample"]={"events":count,"migrations":len(sample),"complete":0,"censored":0}
 for m,z in sample.items():
  if not z["entry"] or not z["exit"]:
   report["sample"]["censored"]+=1;continue
  st,ep,quote=z["entry"];et,xp=z["exit"]
  move=xp/ep-1
  item={"mint":m,"quote_mint":quote,"first_trade_after_migration":st,
        "first_trade_after_5min":et,"entry_price":ep,"exit_price":xp,
        "gross_return_pct":round(move*100,3),"trades":z["trades"]}
  if quote in ("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v","USDC"):
   for name,fixed,fee,slip in (("app",.37,.004,.01),("api_hypothesis",.02,.0175,.01)):
    cash=5*(1-fee)**2*(1-slip)**2*(xp/ep)-fixed
    item[name+"_net_5usdc"]=round(cash-(5+fixed),4)
  report["pairs"].append(item)
 report["sample"]["complete"]=len(report["pairs"])
 report["sample"]["usdc_priced"]=sum("app_net_5usdc" in z for z in report["pairs"])
 if report["pairs"]:
  report["median_gross_pct"]=round(statistics.median(x["gross_return_pct"] for x in report["pairs"]),3)
  for name in ("app","api_hypothesis"):
   arr=[x[name+"_net_5usdc"] for x in report["pairs"] if name+"_net_5usdc" in x]
   report[name]={"count":len(arr),"winners":sum(x>0 for x in arr),"sum_pnl_usdc":round(sum(arr),4)}
except Exception as e:report["error"]=str(e)[:500]
(P/"summary.json").write_text(json.dumps(report,indent=2))
with (P/"pairs.csv").open("w",newline="") as f:
 cols=["mint","quote_mint","first_trade_after_migration","first_trade_after_5min","entry_price","exit_price","gross_return_pct","trades","app_net_5usdc","api_hypothesis_net_5usdc"]
 w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
 for row in report["pairs"]:w.writerow(row)
print(json.dumps({k:v for k,v in report.items() if k!="pairs"},indent=2))
