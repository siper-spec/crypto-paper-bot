"""BOOST migration proxy feature-screen evaluation; two-hour train/holdout.
Only information through 60s after migration used for entering at 60s.
Positions exit at first trade at/after 300s.
No exact BOOST event markers, no wallet secrets, no orders, no cherry-picking.
"""
import csv,json,statistics,collections,io,requests,zstandard,math
from pathlib import Path
from bisect import bisect_left
OUT=Path("pumpfun/boost_feature_results");OUT.mkdir(parents=True,exist_ok=True)
SOL="So11111111111111111111111111111111111111112"
FIELDS=["mint","hour","buy_count","sell_count","buyers","sellers","ratio","net_sol","buyer_concentration","sell_concentration","early_price_change","entry_price","exit_price","gross_pct","net_app_5_usdc","net_api_hypo_5_usdc"]
def f(x):
 try:return float(x)
 except (TypeError,ValueError):return 0.
def read(hour):
 url=f"https://replay.shrine.trade/pump/{hour}.jsonl.zst"
 data={};events=0
 with requests.get(url,timeout=60,stream=True) as r:
  r.raise_for_status()
  stream=zstandard.ZstdDecompressor().stream_reader(r.raw)
  for line in io.TextIOWrapper(stream,encoding="utf-8"):
   events+=1
   try:e=json.loads(line)
   except ValueError:continue
   mint=e.get("mint");t=e.get("timestamp")
   if not mint or not isinstance(t,(int,float)):continue
   if e.get("action")=="migrate" and e.get("protocol")=="PUMPFUN":
    data.setdefault(mint,{"t":t,"trades":[]})
   elif mint in data and e.get("protocol")=="PUMPSWAP" and e.get("action") in ("buy","sell") and e.get("quoteMint")==SOL:
    d=data[mint]
    if not d["t"]<=t<=d["t"]+450:continue
    price=f(e.get("price"))
    if price<=0:continue
    d["trades"].append({"t":t,"p":price,"kind":e["action"],
      "amount":abs(f(e.get("quoteAmount"))),"wallet":e.get("txSigner")})
 return data,events
def make_row(mint,hour,d):
 a=d["t"];trades=sorted(d["trades"],key=lambda x:x["t"])
 first=[t for t in trades if a<=t["t"]<a+60]
 if len(first)<2:return None,"no_early_trades"
 future=[t for t in trades if t["t"]>=a+60]
 if not future:return None,"no_entry"
 exits=[t for t in trades if t["t"]>=a+300]
 if not exits:return None,"no_exit"
 entry=future[0]["p"];exit=exits[0]["p"]
 buys=[t for t in first if t["kind"]=="buy"]
 sells=[t for t in first if t["kind"]=="sell"]
 # Count distinct signers, which is not proof of distinct ultimate wallet owners
 buyers=set(x["wallet"] for x in buys if x["wallet"])
 sellers=set(x["wallet"] for x in sells if x["wallet"])
 bvol=sum(x["amount"] for x in buys);svol=sum(x["amount"] for x in sells)
 count_b=collections.Counter()
 count_s=collections.Counter()
 for x in buys:count_b[str(x["wallet"])]+=x["amount"]
 for x in sells:count_s[str(x["wallet"])]+=x["amount"]
 peak_b=max(count_b.values(),default=0);peak_s=max(count_s.values(),default=0)
 pfirst=first[0]["p"];plast=first[-1]["p"]
 move=exit/entry
 def net(fixed,fee,slip):
  return 5*move*(1-fee)**2*(1-slip)**2-5-2*fixed
 return dict(mint=mint,hour=hour,buy_count=len(buys),sell_count=len(sells),
  buyers=len(buyers),sellers=len(sellers),
  ratio=round(bvol/max(.000001,svol),4),net_sol=round(bvol-svol,5),
  buyer_concentration=round(peak_b/max(.000001,bvol),4),
  sell_concentration=round(peak_s/max(.000001,svol),4),
  early_price_change=round(plast/pfirst-1,5),
  entry_price=entry,exit_price=exit,gross_pct=round((move-1)*100,4),
  net_app_5_usdc=round(net(.37,.004,.01),4),
  net_api_hypo_5_usdc=round(net(.02,.0175,.01),4)),None

FILTERS={
 "baseline":lambda r:True,
 "five_independent_buy_signers":lambda r:r["buyers"]>=5,
 "ten_independent_buy_signers":lambda r:r["buyers"]>=10,
 "buy_volume_exceeds_sell_volume":lambda r:r["ratio"]>=1.5,
 "large_buy_not_dominant":lambda r:r["buyer_concentration"]<=.40,
 "no_strong_early_drop":lambda r:r["early_price_change"]>=-.05,
 "no_strong_early_pump":lambda r:r["early_price_change"]<=.35,
 "combined_basic":lambda r:r["buyers"]>=5 and r["ratio"]>=1.5 and r["buyer_concentration"]<=.5,
 "combined_strict":lambda r:r["buyers"]>=10 and r["ratio"]>=2 and r["buyer_concentration"]<=.4 and -.05<=r["early_price_change"]<=.35,
}
def metrics(rows,fn):
 rows=[r for r in rows if fn(r)]
 if not rows:return {"n":0,"median":None,"mean":None,"wins":0,"hit_rate":None}
 a=[r["net_app_5_usdc"] for r in rows]
 return {"n":len(a),"median":round(statistics.median(a),4),
 "mean":round(statistics.mean(a),4),"wins":sum(x>0 for x in a),
 "hit_rate":round(sum(x>0 for x in a)/len(a),4),
 "median_gross_pct":round(statistics.median(r["gross_pct"] for r in rows),3)}
def main():
 idx=requests.get("https://replay.shrine.trade/pump/index.json",timeout=25).json()
 hrs=idx.get("hours") or []
 if len(hrs)<10:raise RuntimeError("Insufficient archive hours")
 train,test=hrs[-10],hrs[-6]
 full=[];stats=[]
 for hour in (train,test):
  raw,count=read(hour);valid=[];fail=collections.Counter()
  for mint,d in raw.items():
   row,why=make_row(mint,hour,d)
   if row:valid.append(row)
   else:fail[why]+=1
  stats.append({"hour":hour,"events":count,"migrations":len(raw),
    "complete":len(valid),"censored":dict(fail)})
  full.extend(valid)
 if not full:raise RuntimeError("No complete migrated coins")
 with (OUT/"token_features.csv").open("w",newline="") as fp:
  w=csv.DictWriter(fp,fieldnames=FIELDS);w.writeheader();w.writerows(full)
 report={"method":"migration+60s entry to 300s exit, NOT exact BOOST",
 "feature_window":"first 60s after migration, no future leak",
 "train_hour":train,"test_hour":test,"source_stats":stats,"filter_results":{},
 "limitations":["Real BOOST start/end not identified","Quotes are traded price points not guaranteed fills",
 "Different real owners may control multiple wallet addresses",
 "Two hours is small, no statistical validation","Missing end observations excluded",
 "SOL/USD held constant; app fees approximated in USDC","This tests SOL-paired PumpSwap migrations only"]}
 for name,fn in FILTERS.items():
  report["filter_results"][name]={"train":metrics([r for r in full if r["hour"]==train],fn),
    "test":metrics([r for r in full if r["hour"]==test],fn)}
 # Use train sample only to select a rule, requiring at least 8 historical trades.
 elig=[(name,v["train"]["median"]) for name,v in report["filter_results"].items()
    if v["train"]["n"]>=8 and name!="baseline"]
 if elig:
  selected=max(elig,key=lambda x:x[1])[0]
  report["train_selected_filter"]=selected
  report["selected_holdout"]=report["filter_results"][selected]["test"]
 (OUT/"summary.json").write_text(json.dumps(report,indent=2))
 print(json.dumps(report,indent=2))
if __name__=="__main__":main()
