"""Read-only Pump.fun copy-trading wallet shortlist. No keys, trades, or wallet connection."""
import json, math, os, time, urllib.request, urllib.error
from pathlib import Path

ROOT="https://pumpdata.fun"
OUT=Path("pumpfun/copy_research")
OUT.mkdir(parents=True,exist_ok=True)

def get(path):
    req=urllib.request.Request(ROOT+path,headers={"User-Agent":"pumpfun-copy-research/1.0"})
    with urllib.request.urlopen(req,timeout=22) as res:
        return json.load(res)

def num(x):
    try: return float(x)
    except (ValueError,TypeError): return None

def wallets_in(obj):
    """Extract actual full Solana wallet addresses, not truncated display strings."""
    addresses=set()
    def visit(x):
        if isinstance(x,list):
            for v in x: visit(v)
        elif isinstance(x,dict):
            for field in ("address","wallet","wallet_address","walletAddress","pubkey"):
                a=x.get(field)
                if isinstance(a,str) and 32<=len(a)<=44 and all(ch in "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz" for ch in a):
                    addresses.add(a)
            for k,v in x.items():
                if isinstance(v,(dict,list)):visit(v)
    visit(obj)
    return sorted(addresses)

def score(r):
    recent=r.get("recent") or {}
    p=num(r.get("pnl_sol"))
    coins=num(r.get("coins"))
    hold=num(recent.get("median_hold_s"))
    flips=num(recent.get("flip_share"))
    trades=num(recent.get("trades_per_day"))
    snipes=num(recent.get("snipe_share"))
    fast=num(recent.get("fast_share"))
    problems=[]
    if r.get("class")!="winner": problems.append("not_classified_winner")
    if p is None or p<10: problems.append("weak_or_missing_pnl")
    if coins is None or coins<30: problems.append("too_few_coins")
    if hold is None or hold<180: problems.append("too_fast_to_copy")
    if flips is None or flips>=0.15: problems.append("too_many_fast_flips_or_missing")
    if trades is None or trades>20 or trades<1: problems.append("trade_pace_unsuitable")
    if snipes is not None and snipes>0.2: problems.append("sniping")
    if fast is not None and fast>0.3: problems.append("automation_speed")
    if problems:return 0,problems
    # Rank not by PnL alone: punish short hold and high frequency.
    rating=(min(30,7*math.log10(max(p,1)))+min(25,5*math.log10(max(coins,1)))
           +min(25,5*math.log10(max(hold,1)))+20*(1-flips))
    return round(rating,2),[]

def main():
    raw=get("/wallets/top?followable=1&limit=100")
    (OUT/"leaderboard_raw.json").write_text(json.dumps(raw,indent=2))
    addresses=wallets_in(raw)
    rows=[]
    errors=[]
    for i,address in enumerate(addresses[:30]):
        try:
            info=get("/wallet/"+address+".json")
            # Different API response versions may nest wallets under a key.
            r=info.get("wallet") if isinstance(info,dict) and isinstance(info.get("wallet"),dict) else info
            if not isinstance(r,dict): r={}
            s,why=score(r)
            rows.append({"address":address,"score":s,"copy_research_candidate":not why,
                         "reasons":why,"class":r.get("class"),"pnl_sol":r.get("pnl_sol"),
                         "coins":r.get("coins"),"recent":r.get("recent")})
        except (OSError,ValueError) as exc:
            errors.append({"address":address,"error":str(exc)[:140]})
        time.sleep(0.2)
    rows.sort(key=lambda r:r["score"],reverse=True)
    report={"source":"pumpdata.fun", "mode":"READ_ONLY", "wallets_found":len(addresses),
        "wallets_checked":len(rows),"shortlisted":sum(x["copy_research_candidate"] for x in rows),
        "top_candidates":rows[:15],"lookup_errors":errors,
        "historical_follower_profit_eur":None,
        "conclusion":"Wallet ranking only. No actual delayed copy trade replay or verified EUR P&L."}
    (OUT/"copy_wallet_report.json").write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!="top_candidates"},indent=2))
if __name__=="__main__":main()
