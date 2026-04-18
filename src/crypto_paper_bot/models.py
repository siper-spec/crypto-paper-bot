
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
@dataclass
class Candle:
    open_time_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
@dataclass
class IndicatorSnapshot:
    ema_fast: float
    ema_slow: float
    rsi: float
    momentum_pct: float
    last_price: float
@dataclass
class Position:
    symbol: str
    entry_price: float
    quantity: float
    entry_time_ms: int
    stop_loss_price: float
    take_profit_price: float
@dataclass
class TradeRecord:
    side: str
    symbol: str
    price: float
    quantity: float
    timestamp_ms: int
    fee_paid: float
    pnl_eur: float
    reason: str
@dataclass
class PortfolioState:
    cash_eur: float
    position: Optional[Position] = None
    realized_pnl_eur: float = 0.0
    trade_count: int = 0
    wins: int = 0
    losses: int = 0
    last_action: str = "INIT"
@dataclass
class StrategyDecision:
    action: str
    reason: str
    price: float
    indicators: IndicatorSnapshot
