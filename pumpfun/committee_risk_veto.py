"""Committee risk veto for paper trading and future strategy comparison.
Values are estimates only; never sends orders. Never claims future winners.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class Costs:
    fixed_each_side:float=.37
    platform_each_side:float=.004
    slippage_each_side:float=.01

def round_trip_break_even(position_usdc:float,c:Costs=Costs())->float:
    """Minimum price increase required to recover entry + exit costs."""
    if position_usdc<=0:raise ValueError("size")
    net_buy=position_usdc*(1-c.platform_each_side)*(1-c.slippage_each_side)
    effective_sell=(1-c.platform_each_side)*(1-c.slippage_each_side)
    # cash spent at entry includes network fee
    return (position_usdc+2*c.fixed_each_side)/(net_buy*effective_sell)-1

def evaluate_order(position_usdc:float,take_profit_pct:float,
                   stop_loss_pct:float,win_rate_estimate:float|None=None,
                   c:Costs=Costs()):
    be=round_trip_break_even(position_usdc,c)
    gross_exit=position_usdc*(1-c.platform_each_side)*(1-c.slippage_each_side)
    winning_proceeds=gross_exit*(1+take_profit_pct)*(1-c.platform_each_side)*(1-c.slippage_each_side)-c.fixed_each_side
    losing_proceeds=gross_exit*(1-stop_loss_pct)*(1-c.platform_each_side)*(1-c.slippage_each_side)-c.fixed_each_side
    stake=position_usdc+c.fixed_each_side
    win=winning_proceeds-stake;loss=losing_proceeds-stake
    required_win_rate=(-loss/(win-loss)) if win>0 and loss<0 else None
    vetoes=[]
    if take_profit_pct<=be:vetoes.append("target_below_round_trip_break_even")
    if required_win_rate is None:vetoes.append("invalid_payoff_profile")
    if win_rate_estimate is None:vetoes.append("no_out_of_sample_win_rate")
    elif required_win_rate is not None and win_rate_estimate<=required_win_rate+.05:
        vetoes.append("expected_edge_not_established")
    return {"position_usdc":position_usdc,
            "break_even_pct":round(be*100,3),
            "take_profit_pct":take_profit_pct*100,
            "stop_loss_pct":stop_loss_pct*100,
            "net_profit_if_target_hit_usdc":round(win,4),
            "net_loss_if_stop_hit_usdc":round(loss,4),
            "minimum_required_win_rate_pct":round(required_win_rate*100,2) if required_win_rate is not None else None,
            "vetoes":vetoes,"paper_entry_allowed":not vetoes}

if __name__=="__main__":
    import json
    for size in (2,5,10,20):
        print(json.dumps(evaluate_order(size,.3,.12)))
