"""Committee V2: paired, read-only forward-paper experiment.
One token-selection algorithm; the same entries/exits measured under two cost models.
No real orders, wallet keys, signing, account-trade subscriptions, or claimed fills.
"""
import csv,json,math,os,time,datetime,collections,requests
from pathlib import Path

CAPITAL=50.0
SIZE=5.0
COSTS={
 "pump_app_observed_fixed": {"fixed":.37,"percent":.004,"slippage":.01,
      "note":"Observed app order quote approximated $0.37 each side"},
 "local_api_hypothetical": {"fixed":.02,"percent":.0175,"slippage":.01,
      "note":"Hypothetical $0.02 flat, 0.5% PumpPortal + 1.25% pool; NOT verified execution quote"}
}
ALGORITHMS={
 "momentum": {"tp":.30,"stop":-.15,"hold":100},
 "rebound": {"tp":.30,"stop":-.15,"hold":100},
}
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def num(v):
 try:return float(v)
 except (TypeError,ValueError):return 0.0
def proceeds(entry,exit,c):
 return max(0,SIZE*(1-c["percent"])*(1-c["slippage"])*(exit/entry)*(1-c["percent"])*(1-c["slippage"])-c["fixed"])
def breakeven(c):
 a=(1-c["percent"])**2*(1-c["slippage"])**2
 return (SIZE+2*c["fixed"])/(SIZE*a)-1

class Committee:
 def __init__(self):
  self.first=now();self.seen=set();self.history=collections.defaultdict(list)
  self.quotes={};self.errors=[];self.scan_count=0
  self.arms={a+"__"+k:{"algo":a,"cost":k,"cash":CAPITAL,"open":{},"closed":[],"rejections":collections.Counter()}
             for a in ALGORITHMS for k in COSTS}
 def scan(self):
  try:
   x=requests.get("https://api.dexscreener.com/token-boosts/latest/v1",timeout=10)
   x.raise_for_status()
   for t in x.json():
    if t.get("chainId")=="solana" and t.get("tokenAddress"):self.seen.add(t["tokenAddress"])
  except Exception as e:self.errors.append("discovery:"+str(e)[:95])
  out={}
  # Do not exclude last-arriving tokens based on alphanumeric address ordering.
  mints=list(self.seen)[-80:]
  for i in range(0,len(mints),25):
   chunk=mints[i:i+25]
   try:
    r=requests.get("https://api.dexscreener.com/tokens/v1/solana/"+",".join(chunk),timeout=12)
    r.raise_for_status()
    for p in r.json():
     m=(p.get("baseToken") or {}).get("address")
     if m not in chunk or p.get("chainId")!="solana":continue
     price=num(p.get("priceUsd"))
     if price<=0:continue
     t=(p.get("txns") or {}).get("m5") or {}
     q={"price":price,"liq":num((p.get("liquidity") or {}).get("usd")),
        "volume":num((p.get("volume") or {}).get("m5")),
        "buy":int(num(t.get("buys"))),"sell":int(num(t.get("sells"))),
        "symbol":(p.get("baseToken") or {}).get("symbol","?"),"at":time.monotonic()}
     if m not in out or q["liq"]>out[m]["liq"]:out[m]=q
   except Exception as e:self.errors.append("prices:"+str(e)[:100])
  self.scan_count+=1;return out
 def signal(self,m,q,algo):
  h=self.history[m]
  if len(h)<3:return False,"no_history"
  if q["liq"]<12000:return False,"liq"
  if q["volume"]<1400:return False,"volume"
  if q["buy"]+q["sell"]<20:return False,"activity"
  current=q["price"];p0=h[0]["price"];p1=h[-2]["price"]
  if p0<=0 or p1<=0:return False,"bad_price"
  total=current/p0-1;recent=current/p1-1
  if algo=="momentum":
   return (.01<=total<=.35 and recent>0 and q["buy"]>q["sell"]),"not_momentum"
  return (-.25<=total<0 and recent>.005 and q["buy"]>=q["sell"]*.9),"no_rebound"
 def exit(self,arm,m,q,reason):
  pos=arm["open"].pop(m)
  c=COSTS[arm["cost"]];v=proceeds(pos["price"],q["price"],c)
  arm["cash"]+=v
  arm["closed"].append({"mint":m,"symbol":pos["symbol"],"entry_time":pos["time"],
    "exit_time":now(),"reason":reason,"price_buy":pos["price"],"price_sell":q["price"],
    "entry_liquidity":pos["liq"],"exit_liquidity":q["liq"],
    "gross_move_pct":round(100*(q["price"]/pos["price"]-1),3),
    "net_usdc":round(v-(SIZE+c["fixed"]),5)})
 def tick(self,quotes,entry=True):
  for m,q in quotes.items():
   self.history[m].append(q);self.history[m]=self.history[m][-24:]
  for label,arm in self.arms.items():
   algo=ALGORITHMS[arm["algo"]]
   for m,p in list(arm["open"].items()):
    q=quotes.get(m)
    if not q:continue
    move=q["price"]/p["price"]-1
    if move>=algo["tp"]:self.exit(arm,m,q,"take_profit")
    elif move<=algo["stop"]:self.exit(arm,m,q,"observed_stop")
    elif time.monotonic()-p["clock"]>algo["hold"]:self.exit(arm,m,q,"time")
   if not entry:continue
   if len(arm["open"])>=2:continue
   prior=set(arm["open"])|{r["mint"] for r in arm["closed"]}
   choices=[]
   for m,q in quotes.items():
    if m in prior:continue
    ok,reason=self.signal(m,q,arm["algo"])
    if not ok:arm["rejections"][reason]+=1;continue
    recent=q["price"]/self.history[m][-2]["price"]-1
    choices.append((recent,m,q))
   for _,m,q in sorted(choices,reverse=True)[:2-len(arm["open"])]:
    fee=COSTS[arm["cost"]]["fixed"]
    if arm["cash"]<SIZE+fee:break
    arm["cash"]-=SIZE+fee
    arm["open"][m]={"clock":time.monotonic(),"time":now(),"price":q["price"],
      "symbol":q["symbol"],"liq":q["liq"]}
 def run(self,secs):
  end=time.monotonic()+secs
  while time.monotonic()<end:
   self.quotes=self.scan()
   self.tick(self.quotes,entry=time.monotonic()<end-45)
   time.sleep(min(10,max(0,end-time.monotonic())))
  out=Path("pumpfun/committee_v2_results");out.mkdir(parents=True,exist_ok=True)
  result={"started":self.first,"ended":now(),"mode":"paired_forward_quote_paper",
   "unfunded":True,"real_orders":0,"token_selection":"DexScreener boosts (selection bias)",
   "scans":self.scan_count,"discovered":len(self.seen),"cost_models":COSTS,
   "size_usdc":SIZE,"starting_per_arm_usdc":CAPITAL,"arms":{},
   "errors":self.errors[-8:],
   "limits":"Quotes are not executable fills. Cost assumptions especially API flat fees are unverified. No bonding curve full coverage."}
  for label,a in self.arms.items():
   for m in list(a["open"]):
    q=self.quotes.get(m)
    if q and time.monotonic()-q["at"]<45:self.exit(a,m,q,"end_of_session")
   result["arms"][label]={"completed":len(a["closed"]),
      "wins":sum(t["net_usdc"]>0 for t in a["closed"]),
      "net_pnl_usdc":round(sum(t["net_usdc"] for t in a["closed"]),5),
      "unpriced_positions":list(a["open"]),"cash_balance":round(a["cash"],5),
      "theoretical_break_even_move_pct":round(100*breakeven(COSTS[a["cost"]]),3),
      "most_common_rejections":a["rejections"].most_common(6)}
   with (out/(label+".csv")).open("w",newline="") as fp:
    cols=["mint","symbol","entry_time","exit_time","reason","price_buy","price_sell",
     "entry_liquidity","exit_liquidity","gross_move_pct","net_usdc"]
    w=csv.DictWriter(fp,fieldnames=cols);w.writeheader();w.writerows(a["closed"])
  (out/"summary.json").write_text(json.dumps(result,indent=2))
  print(json.dumps(result,indent=2))
if __name__=="__main__":Committee().run(int(os.getenv("SECONDS","240")))
