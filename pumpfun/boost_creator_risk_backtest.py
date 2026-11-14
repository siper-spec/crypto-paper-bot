"""Creator-linked selling and early-seller concentration, historical migration proxy.
No wallet keys. No future features. All outcomes include fees and censored counts.
The creator is only identified when a same-hour PUMPFUN 'create' event links
the mint to its txSigner. Other creators are UNKNOWN, not considered safe.
"""
import requests,zstandard,io,json,csv,collections,statistics
from pathlib import Path
from bisect import bisect_left

DIR=Path("pumpfun/creator_risk_results")
DIR.mkdir(parents=True,exist_ok=True)
SOL="So11111111111111111111111111111111111111112"
def f(x):
 try:return float(x)
 except (ValueError,TypeError):return 0.
def read_hour(hour):
 creators={}
 migrated={}
 events=0
 with requests.get("https://replay.shrine.trade/pump/"+hour+".jsonl.zst",stream=True,timeout=75) as r:
  r.raise_for_status()
  reader=zstandard.ZstdDecompressor().stream_reader(r.raw)
  for line in io.TextIOWrapper(reader,encoding="utf-8"):
   events+=1
   try:e=json.loads(line)
   except (ValueError,TypeError):continue
   mint=e.get("mint");t=e.get("timestamp")
   if not mint or not isinstance(t,(int,float)):continue
   kind=e.get("action");proto=e.get("protocol")
   if kind=="create" and proto in ("PUMPFUN","PUMPFUN_MAYHEM"):
    creator=e.get("txSigner")
    if creator:creators[mint]=creator
   elif kind=="migrate" and proto=="PUMPFUN":
    migrated.setdefault(mint,{"mint":mint,"time":t,"trades":[]})
   elif mint in migrated and proto=="PUMPSWAP" and kind in ("buy","sell") and e.get("quoteMint")==SOL:
    d=migrated[mint]
    if not d["time"]<=t<=d["time"]+450:continue
    price=f(e.get("price"))
    if price>0:d["trades"].append({"time":t,"price":price,
       "action":kind,"signer":e.get("txSigner"),"sol":abs(f(e.get("quoteAmount")))})
 for mint,d in migrated.items():d["creator"]=creators.get(mint)
 return migrated,events,len(creators)

def transform(d,hour):
 ts=d["time"];trades=sorted(d["trades"],key=lambda x:x["time"])
 pre=[x for x in trades if ts<=x["time"]<ts+60]
 after=[x for x in trades if x["time"]>=ts+60]
 exittrades=[x for x in trades if x["time"]>=ts+300]
 if len(pre)<2:return None,"too_few_early_trades"
 if not after:return None,"missing_entry"
 if not exittrades:return None,"missing_exit"
 entry=after[0]["price"];exit=exittrades[0]["price"]
 buys=[x for x in pre if x["action"]=="buy"]
 sells=[x for x in pre if x["action"]=="sell"]
 bvol=sum(x["sol"] for x in buys)
 svol=sum(x["sol"] for x in sells)
 sell_by_wallet=collections.Counter()
 buy_by_wallet=collections.Counter()
 for x in sells:sell_by_wallet[x["signer"] or "unknown"]+=x["sol"]
 for x in buys:buy_by_wallet[x["signer"] or "unknown"]+=x["sol"]
 largest_sell_share=(max(sell_by_wallet.values(),default=0)/svol) if svol>0 else 0
 largest_buy_share=(max(buy_by_wallet.values(),default=0)/bvol) if bvol>0 else 0
 known_creator=bool(d.get("creator"))
 creator_sells=any(x["signer"]==d["creator"] for x in sells) if known_creator else None
 creator_sold_sol=sum(x["sol"] for x in sells if x["signer"]==d["creator"]) if known_creator else None
 move=exit/entry
 # fee model for 5 USDC, proxy: mark-to-market USD rate unchanged
 app=5*move*(1-.004)**2*(1-.01)**2-5-2*.37
 api=5*move*(1-.0175)**2*(1-.01)**2-5-2*.02
 return {"hour":hour,"mint":d["mint"],"creator_known":known_creator,
  "creator_sell_60s":creator_sells,"creator_sol_sold_60s":creator_sold_sol,
  "buyer_wallets":len(set(x["signer"] for x in buys if x["signer"])),
  "seller_wallets":len(set(x["signer"] for x in sells if x["signer"])),
  "buys":len(buys),"sells":len(sells),
  "buy_sol":round(bvol,5),"sell_sol":round(svol,5),
  "sell_buy_ratio":round(svol/max(bvol,.000001),4),
  "largest_sell_share":round(largest_sell_share,4),
  "largest_buy_share":round(largest_buy_share,4),
  "first_60s_price_move_pct":round((pre[-1]["price"]/pre[0]["price"]-1)*100,4),
  "net_app_5":round(app,4),"net_api_5":round(api,4),
  "gross_pct":round((move-1)*100,4)},None

RULES={
 "all":lambda x:True,
 "exclude_confirmed_creator_sells":lambda x:x["creator_sell_60s"] is not True,
 "exclude_concentrated_sells_60pct":lambda x:x["largest_sell_share"]<.60,
 "exclude_concentrated_buys_50pct":lambda x:x["largest_buy_share"]<.50,
 "sell_volume_below_buy_volume":lambda x:x["sell_buy_ratio"]<1,
 "sell_volume_below_half_buy_volume":lambda x:x["sell_buy_ratio"]<.5,
 "exclude_creator_sell_and_seller_concentration":lambda x:x["creator_sell_60s"] is not True and x["largest_sell_share"]<.6,
 "require_creator_identified_no_sells":lambda x:x["creator_sell_60s"] is False,
 "three_filters":lambda x:x["largest_sell_share"]<.6 and x["sell_buy_ratio"]<1 and x["largest_buy_share"]<.5
}
def measure(rows,fn):
 arr=[r["net_app_5"] for r in rows if fn(r)]
 return {"n":len(arr),"wins":sum(p>0 for p in arr),
  "win_rate":round(sum(p>0 for p in arr)/len(arr),4) if arr else None,
  "median_net":round(statistics.median(arr),4) if arr else None,
  "mean_net":round(statistics.mean(arr),4) if arr else None,
  "total_net":round(sum(arr),4),
  "worst_net":round(min(arr),4) if arr else None}

def main():
 idx=requests.get("https://replay.shrine.trade/pump/index.json",timeout=25)
 idx.raise_for_status();hours=idx.json()["hours"]
 train,test=hours[-10],hours[-6]
 allrows=[];metadata=[]
 for hour in (train,test):
  x,events,creators=read_hour(hour)
  rows=[];censored=collections.Counter()
  for d in x.values():
   row,why=transform(d,hour)
   if row:rows.append(row)
   else:censored[why]+=1
  allrows+=rows
  metadata.append({"hour":hour,"events":events,"migrations":len(x),
   "creators_seen_same_hour":creators,
   "creator_identified_in_completed":sum(r["creator_known"] for r in rows),
   "observed_creator_sales":sum(r["creator_sell_60s"] is True for r in rows),
   "completed":len(rows),"censored":dict(censored)})
 if allrows:
  with (DIR/"per_token.csv").open("w",newline="") as fp:
   w=csv.DictWriter(fp,fieldnames=allrows[0].keys())
   w.writeheader();w.writerows(allrows)
 report={"title":"Creator and early-sell risk study, migration proxy",
    "entry":"first PumpSwap trade >=60s after migration",
    "exit":"first PumpSwap trade >=300s after migration",
    "train":train,"holdout":test,"sample_metadata":metadata,
    "results":{},"creator_unknown_handling":"UNKNOWN not SAFE",
    "warning":"NOT BOOST start/end, no verified execution, creator is only linked by same-hour create events; cannot infer insider clusters from signers alone"}
 for name,fn in RULES.items():
  report["results"][name]={"train":measure([r for r in allrows if r["hour"]==train],fn),
                            "holdout":measure([r for r in allrows if r["hour"]==test],fn)}
 # Honest selection on training only; require 8 candidates and reject rules with non-positive median
 allowed=[(name,v["train"]["median_net"]) for name,v in report["results"].items()
  if name!="all" and v["train"]["n"]>=8 and v["train"]["median_net"] is not None]
 if allowed:
  best=max(allowed,key=lambda item:item[1])[0]
  report["selected_from_train"]=best
  report["holdout_selected"]=report["results"][best]["holdout"]
  report["approved_for_live"]=False
 (DIR/"summary.json").write_text(json.dumps(report,indent=2))
 print(json.dumps(report,indent=2))
if __name__=="__main__":main()
