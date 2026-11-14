"""Read-only committee paper experiment. No credentials, signing, swaps or real orders.
Data: DexScreener Solana token boosts/pairs. Boosted candidates are a biased sample.
Each arm observes the same snapshots; NO cherry-picking winners.
"""
from __future__ import annotations
import collections,csv,datetime,json,math,os,time,requests
from pathlib import Path

START=50.0
SIZE=5.0
APP_FIXED=0.37  # USDC per side, observed Pump.fun app quote; not an API execution quote
APP_FEE=.004
SLIP=.01
ARMS={
 "momentum":dict(tp=.18,sl=-.12,hold=120,maxopen=2),
 "rebound":dict(tp=.15,sl=-.10,hold=120,maxopen=2),
 "consensus":dict(tp=.14,sl=-.10,hold=120,maxopen=2),
}
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def num(x):
 try:return float(x)
 except (ValueError,TypeError):return 0.
def sell_value(size,entry,exit):
 return max(0.,size*(1-APP_FEE)*(1-SLIP)*(exit/entry)*(1-APP_FEE)*(1-SLIP)-APP_FIXED)
class Committee:
 def __init__(self,clock=time.monotonic):
  self.clock=clock;self.start=utc();self.market={};self.history=collections.defaultdict(list)
  self.errors=[];self.events=[];self.scans=0;self.seen=set()
  self.arms={n:{"cash":START,"open":{},"trades":[],"rejects":collections.Counter()} for n in ARMS}
 def discover(self):
  try:
   response=requests.get("https://api.dexscreener.com/token-boosts/latest/v1",timeout=15)
   response.raise_for_status()
   arr=response.json()
   for it in arr:
    if it.get("chainId")=="solana" and isinstance(it.get("tokenAddress"),str):
     self.seen.add(it["tokenAddress"])
  except Exception as e:self.errors.append("discovery "+str(e)[:130])
 def snapshot(self):
  self.discover()
  # 80 tokens max to reduce API requests; deterministic sort for audit.
  addresses=sorted(self.seen)[:80]
  quotes={}
  for idx in range(0,len(addresses),25):
   batch=addresses[idx:idx+25]
   try:
    r=requests.get("https://api.dexscreener.com/tokens/v1/solana/"+",".join(batch),timeout=15)
    r.raise_for_status()
    for p in r.json():
     if p.get("chainId")!="solana":continue
     mint=(p.get("baseToken") or {}).get("address")
     if mint not in batch:continue
     price=num(p.get("priceUsd"));liq=num((p.get("liquidity") or {}).get("usd"))
     if price<=0:continue
     tx=(p.get("txns") or {}).get("m5") or {}
     v=(p.get("volume") or {})
     q={"price":price,"liq":liq,"buy":int(num(tx.get("buys"))),
      "sell":int(num(tx.get("sells"))),"vol5":num(v.get("m5")),
      "cap":num(p.get("marketCap") or p.get("fdv")),
      "symbol":(p.get("baseToken") or {}).get("symbol","?"),
      "dex":p.get("dexId","?"),"at":self.clock()}
     if mint not in quotes or liq>quotes[mint]["liq"]:quotes[mint]=q
   except Exception as e:self.errors.append("quotes "+str(e)[:130])
  self.scans+=1
  return quotes
 def scores(self,m,q):
  h=self.history[m]
  if len(h)<2:return None,"insufficient_history"
  # Fees, sellability and concentration are the risk team's responsibility.
  if q["liq"]<8000:return None,"low_liquidity"
  if q["vol5"]<1000:return None,"low_volume"
  if q["buy"]+q["sell"]<15:return None,"low_activity"
  recent=q["price"]/h[-2]["price"]-1
  longer=q["price"]/h[0]["price"]-1
  pressure=q["buy"]/max(1,q["sell"])
  if not math.isfinite(longer):return None,"bad_price"
  quant_momentum=2*longer+recent+min(2,pressure)/10
  quant_rebound=(-longer)+2*recent+min(2,pressure)/10
  smart_proxy=(min(q["vol5"]/max(q["liq"],1),1)*.4
   +min(pressure,3)*.1+min(q["liq"]/40000,1)*.3)
  # This is a market-activity proxy, NOT authenticated smart-wallet copying.
  return {"momentum":quant_momentum,"rebound":quant_rebound,
          "consensus":(quant_momentum+quant_rebound)/2+smart_proxy},None
 def exit_trade(self,arm,m,q,reason):
  o=arm["open"].pop(m)
  value=sell_value(o["size"],o["price"],q["price"])
  arm["cash"]+=value
  arm["trades"].append({"mint":m,"symbol":o["symbol"],"reason":reason,
    "entry_time":o["entered"],"exit_time":utc(),
    "entry_price":o["price"],"exit_price":q["price"],
    "entry_liquidity_usd":o["liquidity"],"exit_liquidity_usd":q["liq"],
    "pnl_usdc":round(value-o["spent"],5),
    "net_return_pct":round(100*(value/o["spent"]-1),2)})
 def step(self,quotes,allow=True):
  for m,q in quotes.items():
   self.history[m].append(q);self.history[m]=self.history[m][-30:]
  for name,arm in self.arms.items():
   cfg=ARMS[name]
   for m,o in list(arm["open"].items()):
    q=quotes.get(m)
    if not q:continue
    ret=q["price"]/o["price"]-1
    if ret>=cfg["tp"]:self.exit_trade(arm,m,q,"take_profit")
    elif ret<=cfg["sl"]:self.exit_trade(arm,m,q,"observed_stop")
    elif self.clock()-o["time"]>=cfg["hold"]:self.exit_trade(arm,m,q,"timeout")
   if not allow:continue
   rank=[]
   traded={t["mint"] for t in arm["trades"]}
   for m,q in quotes.items():
    if m in arm["open"] or m in traded:continue
    scores,reason=self.scores(m,q)
    if reason:arm["rejects"][reason]+=1;continue
    s=scores[name]
    if name=="momentum" and not(.001<=q["price"]/self.history[m][0]["price"]-1<=.3):
     arm["rejects"]["momentum_not_positive"]+=1;continue
    if name=="rebound" and not(q["price"]/self.history[m][0]["price"]-1<0 and
                                q["price"]>=self.history[m][-2]["price"]):
     arm["rejects"]["no_rebound"]+=1;continue
    if name=="consensus" and not(s>.18 and q["buy"]>=q["sell"]):
     arm["rejects"]["weak_consensus"]+=1;continue
    rank.append((s,m,q))
   slots=max(0,cfg["maxopen"]-len(arm["open"]))
   for score,m,q in sorted(rank,key=lambda x:x[0],reverse=True)[:slots]:
    if arm["cash"]<SIZE+APP_FIXED:break
    arm["cash"]-=SIZE+APP_FIXED
    arm["open"][m]={"size":SIZE,"spent":SIZE+APP_FIXED,"price":q["price"],
       "symbol":q["symbol"],"time":self.clock(),"entered":utc(),
       "liquidity":q["liq"],"score":round(score,5)}
    self.events.append({"strategy":name,"event":"paper_buy","mint":m,
     "symbol":q["symbol"],"quote_usd":q["price"],"liquidity":q["liq"],
     "score":round(score,5),"at":utc()})
 def finish(self):
  out=Path("pumpfun/committee_results");out.mkdir(parents=True,exist_ok=True)
  report={"mode":"read_only_quote_paper","began":self.start,"ended":utc(),
   "source":"DEXScreener boosted Solana tokens (selection bias)",
   "scans":self.scans,"tokens_seen":len(self.seen),
   "wallet_copying":False,"capital_per_arm_usdc":START,
   "size_per_trade_usdc":SIZE,
   "cost_model":{"app_network_each_side_usdc":APP_FIXED,
     "platform_each_side_pct":APP_FEE*100,
     "slippage_each_side_pct":SLIP*100},
   "strategies":{},"errors":self.errors[-8:],
   "note":"No actual fills. Non-DEX bonding-curve coins not covered; boosted pool selection bias; missing quote means position unpriced."}
  for name,arm in self.arms.items():
   for m,o in list(arm["open"].items()):
    q=self.market.get(m)
    if q and self.clock()-q["at"]<45:self.exit_trade(arm,m,q,"session_end")
   realized=sum(x["pnl_usdc"] for x in arm["trades"])
   report["strategies"][name]={"entries":len(arm["trades"])+len(arm["open"]),
    "closed":len(arm["trades"]),"wins":sum(x["pnl_usdc"]>0 for x in arm["trades"]),
    "pnl_usdc":round(realized,5),"cash_usdc":round(arm["cash"],5),
    "unpriced_positions":list(arm["open"]),"top_rejections":arm["rejects"].most_common(5)}
   with (out/(name+"_trades.csv")).open("w",newline="") as f:
    columns=["mint","symbol","reason","entry_time","exit_time","entry_price","exit_price",
    "entry_liquidity_usd","exit_liquidity_usd","pnl_usdc","net_return_pct"]
    writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader();writer.writerows(arm["trades"])
  (out/"summary.json").write_text(json.dumps(report,indent=2))
  (out/"entries.json").write_text(json.dumps(self.events,indent=2))
  print(json.dumps(report,indent=2))
  return report
 def run(self,seconds):
  end=self.clock()+seconds
  while self.clock()<end:
   quotes=self.snapshot()
   self.market=quotes
   self.step(quotes,allow=self.clock()<end-45)
   time.sleep(min(10,max(0,end-self.clock())))
  return self.finish()
if __name__=="__main__":
 Committee().run(int(os.getenv("SESSION_SECONDS","240")))
