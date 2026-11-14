"""Historical migration-proxy grid: multiple entry delays and fixed exits.
NOT an exact BOOST replay. No start/end buyback markers in archived trade events.
Censor missing exits; never use future prices to decide entry.
"""
from __future__ import annotations
import requests,zstandard,io,json,csv,statistics,collections
from bisect import bisect_left
from pathlib import Path
DIR=Path("pumpfun/boost_grid_results");DIR.mkdir(parents=True,exist_ok=True)
OUT={"source":"Shrine historical JSONL trades","exact_boost":False,
     "description":"First PumpSwap trade after migration plus entry delay, exit at first trade at/after clock horizon",
     "hours":[],"grid":[],"limitations":["Not BOOST event start/end data","No executable quotes",
     "SOL quote held constant versus USD for fee model","Hours selected by archive index; missing exits censored",
     "Multiple strategies tested; winners may be selection artifacts"]}
ENTRY=(0,30,60)
EXIT=(60,120,180,240,300,420,600)
SIZES=(5,10,20)
COSTS={"app":(.37,.004,.01),"api_hypothesis":(.02,.0175,.01)}
SOL="So11111111111111111111111111111111111111112"
def net(move,size,c):
 fixed,fee,slip=c
 return size*move*(1-fee)**2*(1-slip)**2-size-2*fixed
def fetch_hour(hour):
 records={};migrations=0;events=0
 url="https://replay.shrine.trade/pump/"+hour+".jsonl.zst"
 with requests.get(url,stream=True,timeout=55) as r:
  r.raise_for_status()
  raw=zstandard.ZstdDecompressor().stream_reader(r.raw)
  for line in io.TextIOWrapper(raw,encoding="utf8"):
   events+=1
   try:e=json.loads(line)
   except ValueError:continue
   mint=e.get("mint");ts=e.get("timestamp")
   if not mint or not isinstance(ts,(int,float)):continue
   protocol=e.get("protocol");action=e.get("action")
   if action=="migrate" and protocol=="PUMPFUN":
    if mint not in records:
     records[mint]={"mint":mint,"at":ts,"trades":[]}
     migrations+=1
   elif mint in records and protocol=="PUMPSWAP" and action in ("buy","sell"):
    if e.get("quoteMint")!=SOL:continue
    z=records[mint]
    if ts<z["at"] or ts>z["at"]+720:continue
    try:p=float(e.get("price"))
    except (TypeError,ValueError):continue
    if p>0:z["trades"].append((ts,p))
 return records,events,migrations

try:
 r=requests.get("https://replay.shrine.trade/pump/index.json",timeout=20);r.raise_for_status()
 hours=r.json()["hours"]
 # two nonadjacent hours available safely before archive tip
 picked=[hours[-6],hours[-10]]
 dataset=[]
 for hour in picked:
  rec,events,migrations=fetch_hour(hour)
  valid=sum(bool(z["trades"]) for z in rec.values())
  OUT["hours"].append({"hour":hour,"events":events,"migrations":migrations,"sol_trade_migrations":valid})
  for z in rec.values():
   z["trades"].sort()
   z["hour"]=hour
   dataset.append(z)
 for h in picked:
  subset=[z for z in dataset if z["hour"]==h]
  for en in ENTRY:
   for duration in EXIT:
    if duration<=en:continue
    for sz in SIZES:
     for name,cost in COSTS.items():
      vals=[];gross=[];censored=0;entered=0;winners=0
      for z in subset:
       xs=z["trades"];ts=[v[0] for v in xs]
       a=bisect_left(ts,z["at"]+en)
       if a>=len(xs):
        censored+=1;continue
       entered+=1
       b=bisect_left(ts,z["at"]+duration)
       if b>=len(xs):
        censored+=1;continue
       move=xs[b][1]/xs[a][1]
       pnl=net(move,sz,cost)
       vals.append(pnl);gross.append(move-1)
       winners+=(pnl>0)
      if vals:
       sorted_vals=sorted(vals)
       # trim one largest and one smallest for outlier sensitivity, if enough data
       trimmed=sorted_vals[1:-1] if len(vals)>=8 else sorted_vals
       OUT["grid"].append({"hour":h,"entry_s":en,"exit_s":duration,
          "size_usdc":sz,"cost":name,"observations":len(vals),
          "entered":entered,"censored":censored,"wins":winners,
          "win_rate":round(winners/len(vals),4),
          "median_pnl":round(statistics.median(vals),4),
          "mean_pnl":round(statistics.mean(vals),4),
          "trimmed_mean_pnl":round(statistics.mean(trimmed),4),
          "median_gross_pct":round(100*statistics.median(gross),3),
          "min_pnl":round(min(vals),4),"max_pnl":round(max(vals),4)})
except Exception as e:
 OUT["error"]=str(e)[:500]
(DIR/"summary.json").write_text(json.dumps({k:v for k,v in OUT.items() if k!="grid"},indent=2))
(DIR/"grid.json").write_text(json.dumps(OUT["grid"],indent=2))
if OUT["grid"]:
 with (DIR/"grid.csv").open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(OUT["grid"][0]))
  w.writeheader();w.writerows(OUT["grid"])
 # fixed representative size & cost, choose horizon only on older hour, check on newer
 older=picked[1];newer=picked[0]
 train=[z for z in OUT["grid"] if z["hour"]==older and z["size_usdc"]==5
   and z["cost"]=="app" and z["observations"]>=10]
 if train:
  best=max(train,key=lambda x:(x["median_pnl"],x["trimmed_mean_pnl"]))
  match=next((z for z in OUT["grid"] if z["hour"]==newer and z["entry_s"]==best["entry_s"]
    and z["exit_s"]==best["exit_s"] and z["size_usdc"]==5 and z["cost"]=="app"),None)
  verdict={"selection_hour":older,"validation_hour":newer,"chosen_by_training_median":best,
           "held_out_result":match,
           "caution":"This is only a two-hour exploratory split, not independently validated edge."}
  (DIR/"holdout.json").write_text(json.dumps(verdict,indent=2))
  print(json.dumps(verdict,indent=2))
print(json.dumps({"hours":OUT["hours"],"rows":len(OUT["grid"]),"error":OUT.get("error")},indent=2))
