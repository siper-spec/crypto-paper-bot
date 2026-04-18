
from __future__ import annotations
from .config import SETTINGS
from .models import PortfolioState, StrategyDecision, IndicatorSnapshot
def decide(portfolio: PortfolioState, indicators: IndicatorSnapshot, latest_time_ms: int) -> StrategyDecision:
    price = indicators.last_price
    if portfolio.position is None:
        long_trend = indicators.ema_fast > indicators.ema_slow
        rsi_ok = SETTINGS.min_rsi_for_entry <= indicators.rsi <= SETTINGS.max_rsi_for_entry
        momentum_ok = indicators.momentum_pct >= SETTINGS.min_momentum_pct
        if long_trend and rsi_ok and momentum_ok:
            return StrategyDecision(action="BUY", reason="EMA momentum + RSI confirmation", price=price, indicators=indicators)
        return StrategyDecision(action="HOLD", reason="No entry setup", price=price, indicators=indicators)
    position = portfolio.position
    held_minutes = max(0.0, (latest_time_ms - position.entry_time_ms) / 60000.0)
    if price <= position.stop_loss_price:
        return StrategyDecision(action="SELL", reason="Stop loss hit", price=price, indicators=indicators)
    if price >= position.take_profit_price:
        return StrategyDecision(action="SELL", reason="Take profit hit", price=price, indicators=indicators)
    if indicators.ema_fast < indicators.ema_slow and indicators.rsi < 48:
        return StrategyDecision(action="SELL", reason="Momentum reversal", price=price, indicators=indicators)
    if held_minutes >= SETTINGS.max_hold_minutes:
        return StrategyDecision(action="SELL", reason="Max hold time reached", price=price, indicators=indicators)
    return StrategyDecision(action="HOLD", reason="Position open", price=price, indicators=indicators)
