"""Read-only LIVE Pump.fun paper test. No wallet or transaction signing."""
import os,time,json,threading,csv,collections,datetime,requests,websocket
from pathlib import Path
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def f(v):
 try:return float(v)
 except (ValueError,TypeError):return 0.0
class Bot:
 def __init__(self):
  self.start=now();self.launch={};self.creator=collections.Counter();self.hist={};self.open={};self.closed=[];self.cash=50.;self.count=collections.Counter();self.errors=[]
 def feed(self,end):
  while time.monotonic()<end:
   ws=None
   try:
    ws=websocket.create_connection('wss://pumpportal.fun/api/data',timeout=8)
    ws.send(json.dumps({'method':'subscribeNewToken'}))
    while time.monotonic()<end:
     ws.settimeout(3)
     try:a=json.loads(ws.recv())
     except websocket.WebSocketTimeoutException:continue
     if not isinstance(a,dict) or not a.get('mint'):continue
     m=a['mint']
     if m not in self.launch:
      c=a.get('traderPublicKey')
      self.launch[m]={'symbol':a.get('symbol'),'creator':c,'t':time.monotonic(),'timestamp':now()}
      self.creator[c]+=1;self.count['launches']+=1
   except Exception as e:self.errors.append('feed '+str(e)[:80]);time.sleep(3)
   finally:
    if ws:
     try:ws.close()
     except Exception:pass
 def prices(self):
  m=list(dict.fromkeys(list(self.open)+list(self.launch)[-60:]))[-75:];quotes={}
  for i in range(0,len(m),25):
   try:
    r=requests.get('https://api.dexscreener.com/tokens/v1/solana/'+','.join(m[i:i+25]),timeout=10)
    r.raise_for_status()
    for p in r.json():
     a=(p.get('baseToken') or {}).get('address')
     if a not in m or p.get('chainId')!='solana' or f(p.get('priceUsd'))<=0:continue
     t=p.get('txns',{}).get('m5',{})
     q={'p':f(p['priceUsd']),'l':f((p.get('liquidity') or {}).get('usd')),
       'cap':f(p.get('marketCap') or p.get('fdv')),'buy':int(t.get('buys') or 0),'sell':int(t.get('sells') or 0),'time':time.monotonic()}
     if a not in quotes or q['l']>quotes[a]['l']:quotes[a]=q
   except Exception as e:self.count['price_errors']+=1;self.errors.append('price '+str(e)[:80])
  return quotes
 def exit(self,m,q,why):
  o=self.open.pop(m);gross=o['units']*q['p']/o['price']
  proceeds=max(0,gross*(1-.0175)*(.98)-.02)
  self.cash+=proceeds
  self.closed.append({'mint':m,'symbol':o['symbol'],'entered':o['entered'],'exited':now(),
   'reason':why,'buy_price':o['price'],'sell_price':q['p'],
   'net_profit_eur':round(proceeds-o['spent'],5),'proceeds_eur':round(proceeds,5)})
 def tick(self,quotes,allow):
  for m,q in quotes.items():self.hist.setdefault(m,[]).append(q);self.hist[m]=self.hist[m][-10:]
  for m,o in list(self.open.items()):
   q=quotes.get(m)
   if not q:continue
   mult=q['p']/o['price']
   if mult<=.70:self.exit(m,q,'observed_stop')
   elif mult>=1.5:self.exit(m,q,'observed_take_profit')
   elif time.monotonic()-o['t']>=150:self.exit(m,q,'time_limit')
  if not allow:return
  choices=[]
  for m,q in quotes.items():
   launch=self.launch.get(m);hist=self.hist.get(m,[])
   if not launch or m in self.open or any(t['mint']==m for t in self.closed):continue
   age=time.monotonic()-launch['t']
   if not 35<=age<=360 or len(hist)<3:continue
   if self.creator[launch['creator']]>=3:continue
   if not 10000<=q['cap']<=100000 or q['l']<1000:continue
   if q['buy']<12 or q['buy']<1.5*max(1,q['sell']):continue
   mom=q['p']/hist[0]['p']-1
   if .03<=mom<=.25:choices.append((mom,m,q))
  for _,m,q in sorted(choices,reverse=True)[:max(0,2-len(self.open))]:
   if self.cash<2.02:break
   self.cash-=2.02
   self.open[m]={'symbol':self.launch[m]['symbol'],'entered':now(),'price':q['p'],
    't':time.monotonic(),'units':2*(1-.0175)*(.98),'spent':2.02}
 def run(self,seconds=540):
  end=time.monotonic()+seconds
  threading.Thread(target=self.feed,args=(end,),daemon=True).start()
  while time.monotonic()<end:
   q=self.prices()
   self.tick(q,allow=time.monotonic()<end-180)
   time.sleep(min(15,max(0,end-time.monotonic())))
  unresolved=[]
  for m in list(self.open):
   h=self.hist.get(m,[])
   if h and time.monotonic()-h[-1]['time']<120:self.exit(m,h[-1],'session_end')
   else:unresolved.append(m)
  # Unresolved positions are not counted as realized profit.
  outcome={'strategy':'public_launch_momentum_baseline','real_orders':False,'wallet_copying':False,
   'started':self.start,'ended':now(),'starting_balance_eur':50.,
   'cash_ending_eur':round(self.cash,5),'realized_pnl_eur':round(self.cash-50,5) if not unresolved else None,
   'open_unresolved':unresolved,'trades_completed':len(self.closed),'launches':len(self.launch),
   'quote_samples':sum(len(v) for v in self.hist.values()),
   'price_error_count':self.count['price_errors'],'errors':self.errors[-8:],
   'fee_per_side_assumed_pct':1.75,'slippage_per_side_assumed_pct':2.0,
   'fixed_fee_per_order_assumed_eur':.02,
   'limitations':'DEX screen quotes not guaranteed executable; momentum only, no account trade stream'}
  d=Path('pumpfun/paper_results');d.mkdir(parents=True,exist_ok=True)
  (d/'summary.json').write_text(json.dumps(outcome,indent=2))
  with (d/'trades.csv').open('w',newline='') as h:
   columns=['mint','symbol','entered','exited','reason','buy_price','sell_price','net_profit_eur','proceeds_eur']
   w=csv.DictWriter(h,fieldnames=columns);w.writeheader();w.writerows(self.closed)
  print(json.dumps(outcome,indent=2))
if __name__=='__main__':Bot().run(int(os.getenv('SESSION_SECONDS','540')))
