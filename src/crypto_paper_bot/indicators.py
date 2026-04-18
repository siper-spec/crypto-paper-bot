
from __future__ import annotations
from typing import List
from .models import Candle, IndicatorSnapshot
def ema(values: List[float], period: int) -> List[float]:
    if not values:
        return []
    alpha = 2.0 / (period + 1.0)
    out = [values[0]]
    for value in values[1:]:
        out.append((alpha * value) + ((1.0 - alpha) * out[-1]))
    return out
def rsi(values: List[float], period: int) -> List[float]:
    if len(values) < 2:
        return [50.0 for _ in values]
    gains = [0.0]
    losses = [0.0]
    for i in range(1, len(values)):
        delta = values[i] - values[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains[1:period+1]) / period if len(values) > period else sum(gains[1:]) / max(1, len(gains)-1)
    avg_loss = sum(losses[1:period+1]) / period if len(values) > period else sum(losses[1:]) / max(1, len(losses)-1)
    rsis = [50.0] * len(values)
    start = min(period + 1, len(values))
    for i in range(start, len(values)):
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period
        if avg_loss == 0:
            rsis[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsis[i] = 100.0 - (100.0 / (1.0 + rs))
    return rsis
def build_snapshot(candles: List[Candle], ema_fast_period: int, ema_slow_period: int, rsi_period: int) -> IndicatorSnapshot:
    closes = [c.close for c in candles]
    fast = ema(closes, ema_fast_period)
    slow = ema(closes, ema_slow_period)
    rsis = rsi(closes, rsi_period)
    momentum_pct = 0.0
    if len(closes) >= 6:
        momentum_pct = (closes[-1] / closes[-6]) - 1.0
    return IndicatorSnapshot(ema_fast=fast[-1], ema_slow=slow[-1], rsi=rsis[-1], momentum_pct=momentum_pct, last_price=closes[-1])
