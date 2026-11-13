import os,time,json,threading,csv,collections,datetime,requests,websocket
from pathlib import Path
BASE=50.;SIZE=2.;FEE=.0175;SLIP=.02;FLAT=.02
RULES={
 "conservative":dict(liq=2500,caplo=10000,caphi=100000,buys=12,ratio=1.5,momlo=.03,momhi=.3,age=35,maxage=420,creator=2,obs=3,tp=1.5,stop=.7,hold=150),
 "balanced":dict(liq=500,caplo=4000,caphi=500000,buys=5,ratio=1.1,momlo=0,momhi=.8,age=20,maxage=600,creator=3,obs=2,tp=1.35,stop=.65,hold=120),
 "aggressive":dict(liq=100,caplo=0,caphi=1000000,buys=0,ratio=0,momlo=-.3,momhi=2,age=10,maxage=900,creator=999,obs=2,tp=1.25,stop=.6,hold=90)}
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def f(x):
 try:return float(x)
 except (TypeError,ValueError):return 0.
def proceeds(units,p):return max(0,units*p*(1-FEE)*(1-SLIP)-FLAT)
class Engine:
 def __init__(self,clock=time.monotonic):
  self.clock=clock;self.start=now();self.launch={};self.creators=collections.Counter()
  self.hist=collections.defaultdict(list);self.lock=threading.Lock();self.errors=[];self.samples=0
  self.arms={k:dict(cash=BASE,open={},trades=[],reject=collections.Counter(),entries=0) for k in RULES}
 def feed(self,end):
  while self.clock()<end:
   ws=None
   try:
    ws=websocket.create_connection("wss://pumpportal.fun/api/data",timeout=12)
    ws.send(json.dumps({"method":"subscribeNewToken"}))
    while self.clock()<end:
     ws.settimeout(3)
     try:d=json.loads(ws.recv())
     except websocket.WebSocketTimeoutException:continue
     except ValueError:continue
     if not isinstance(d,dict) or not d.get("mint"):continue
     with self.lock:
      if d["mint"] not in self.launch:
       c=d.get("traderPublicKey");self.launch[d["mint"]]=dict(at=self.clock(),creator=c,symbol=d.get("symbol"));self.creators[c]+=1
   except Exception as e:self.errors.append("feed "+str(e)[:90]);time.sleep(2)
   finally:
    if ws:
     try:ws.close()
     except Exception:pass
 def quotes(self):
  with self.lock:mints=list(self.launch)[-90:]
  for a in self.arms.values():mints.extend(a["open"])
  mints=list(dict.fromkeys(mints));out={}
  for i in range(0,len(mints),25):
   part=mints[i:i+25]
   try:
    res=requests.get("https://api.dexscreener.com/tokens/v1/solana/"+",".join(part),timeout=12);res.raise_for_status()
    for p in res.json():
     if p.get("chainId")!="solana":continue
     m=(p.get("baseToken") or {}).get("address")
     if m not in part or f(p.get("priceUsd"))<=0:continue
     tx=(p.get("txns") or {}).get("m5") or {}
     q=dict(price=f(p["priceUsd"]),liquidity=f((p.get("liquidity") or {}).get("usd")),
       cap=f(p.get("marketCap") or p.get("fdv")),buys=int(f(tx.get("buys"))),
       sells=int(f(tx.get("sells"))),observed=self.clock())
     if m not in out or q["liquidity"]>out[m]["liquidity"]:out[m]=q
   except Exception as e:self.errors.append("quotes "+str(e)[:90])
  self.samples+=len(out);return out
 def reject(self,m,q,r):
  launch=self.launch.get(m)
  if not launch:return "no_launch"
  age=self.clock()-launch["at"]
  if not r["age"]<=age<=r["maxage"]:return "age"
  if self.creators[launch["creator"]]>r["creator"]:return "creator"
  if q["liquidity"]<r["liq"]:return "liquidity"
  if not r["caplo"]<=q["cap"]<=r["caphi"]:return "cap"
  if q["buys"]<r["buys"]:return "buys"
  if q["buys"]<q["sells"]*r["ratio"]:return "ratio"
  if len(self.hist[m])<r["obs"]:return "observations"
  mom=q["price"]/self.hist[m][0]["price"]-1
  if not r["momlo"]<=mom<=r["momhi"]:return "momentum"
  return None
 def sell(self,a,m,q,why):
  x=a["open"].pop(m);gross=proceeds(x["units"],q["price"]);a["cash"]+=gross
  a["trades"].append(dict(mint=m,symbol=x["symbol"],entry_time=x["time"],
   exit_time=now(),entry_quote=x["price"],exit_quote=q["price"],
   reason=why,pnl_eur=round(gross-x["spent"],6)))
 def tick(self,quotes,enter=True):
  for m,q in quotes.items():
   self.hist[m].append(q);self.hist[m]=self.hist[m][-12:]
  for name,a in self.arms.items():
   r=RULES[name]
   for m,x in list(a["open"].items()):
    q=quotes.get(m)
    if not q:continue
    mult=q["price"]/x["price"];age=self.clock()-x["at"]
    if mult>=r["tp"]:self.sell(a,m,q,"take_profit")
    elif mult<=r["stop"]:self.sell(a,m,q,"observed_stop")
    elif age>=r["hold"]:self.sell(a,m,q,"time_exit")
   if not enter:continue
   used=set(a["open"])|{t["mint"] for t in a["trades"]}
   candidates=[]
   for m,q in quotes.items():
    if m in used:continue
    reason=self.reject(m,q,r)
    if reason:a["reject"][reason]+=1;continue
    mom=q["price"]/self.hist[m][0]["price"]-1
    score=mom+min(1,q["buys"]/(1+q["sells"]))/5+min(1,q["liquidity"]/20000)
    candidates.append((score,m,q))
   for score,m,q in sorted(candidates,reverse=True)[:max(0,3-len(a["open"]))]:
    if a["cash"]<SIZE+FLAT:break
    a["cash"]-=SIZE+FLAT
    a["open"][m]=dict(price=q["price"],units=SIZE*(1-FEE)*(1-SLIP)/q["price"],
      at=self.clock(),time=now(),symbol=self.launch[m]["symbol"],spent=SIZE+FLAT)
    a["entries"]+=1
 def finish(self):
  path=Path("pumpfun/compare_results");path.mkdir(parents=True,exist_ok=True)
  report=dict(start=self.start,end=now(),mode="paper_only_quote_based",launches=len(self.launch),
    quote_observations=self.samples,errors=self.errors[-10:],strategy={},fee_pct_each_side=FEE*100,
    slippage_pct_each_side=SLIP*100,fixed_eur_each_side=FLAT,
    warning="Not actual fills or a validated trading edge; zero real-money trades.")
  for name,a in self.arms.items():
   for m,x in list(a["open"].items()):
    if self.hist[m] and self.clock()-self.hist[m][-1]["observed"]<60:
     self.sell(a,m,self.hist[m][-1],"session_end")
   report["strategy"][name]=dict(entries=a["entries"],completed=len(a["trades"]),
    realized_pnl_eur=round(sum(t["pnl_eur"] for t in a["trades"]),5),
    cash_eur=round(a["cash"],5),unresolved=list(a["open"]),
    top_rejections=a["reject"].most_common(8))
   with (path/(name+"_trades.csv")).open("w",newline="") as fp:
    columns=["mint","symbol","entry_time","exit_time","entry_quote","exit_quote","reason","pnl_eur"]
    w=csv.DictWriter(fp,fieldnames=columns);w.writeheader();w.writerows(a["trades"])
  (path/"summary.json").write_text(json.dumps(report,indent=2))
  print(json.dumps(report,indent=2))
  return report
 def run(self,seconds=600):
  end=self.clock()+seconds
  threading.Thread(target=self.feed,args=(end,),daemon=True).start()
  while self.clock()<end:
   self.tick(self.quotes(),enter=self.clock()<end-180)
   time.sleep(min(12,max(0,end-self.clock())))
  return self.finish()
if __name__=="__main__":Engine().run(int(os.getenv("SESSION_SECONDS","600")))
