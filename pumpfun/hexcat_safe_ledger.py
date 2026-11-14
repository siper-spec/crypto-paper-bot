"""HEXCAT safe ledger replacement. Intended for testing, never enables trading.
Original project: https://github.com/MyWestLord/hexcat (MIT).
"""
from __future__ import annotations
from dataclasses import dataclass,field

@dataclass
class Exits:
    tp_ladder: list[tuple[float,float]]=field(default_factory=lambda:[(1.,.4),(3.,.4)])
    trailing_runner_pct: float=20.
    stop_loss_pct: float=35.

@dataclass
class Position:
    mint:str
    symbol:str
    entry:float
    size_sol:float
    left:float=1.
    peak:float=0.
    hit:set[int]=field(default_factory=set)

@dataclass
class Ledger:
    ex:Exits
    realized_sol:float=0.
    wins:int=0
    losses:int=0
    def step(self,p:Position,price:float)->list[tuple[str,float]]:
        if p.entry<=0 or price<=0 or p.left<=0:
            return []
        p.peak=max(p.peak,price)
        gain=price/p.entry-1
        if gain<=-self.ex.stop_loss_pct/100:
            return [("SL",p.left)]
        out=[]
        available=p.left
        for i,(tp,frac) in enumerate(self.ex.tp_ladder):
            if gain>=tp and i not in p.hit and available>0:
                allocated=min(frac,available)
                p.hit.add(i)
                out.append((f"TP{i+1}",allocated))
                available-=allocated
        if (len(p.hit)==len(self.ex.tp_ladder) and available>0
            and price<=p.peak*(1-self.ex.trailing_runner_pct/100)):
            out.append(("runner",available))
        return out
    def book(self,pnl_sol:float):
        self.realized_sol+=pnl_sol
        if pnl_sol>=0:self.wins+=1
        else:self.losses+=1
