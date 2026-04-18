
from __future__ import annotations
from typing import Any, List
import requests
from .config import SETTINGS
from .models import Candle
class BinanceMarketDataClient:
    def __init__(self) -> None:
        self.session = requests.Session()
    def fetch_candles(self) -> List[Candle]:
        params = {"symbol": SETTINGS.symbol, "interval": SETTINGS.interval, "limit": SETTINGS.candle_limit}
        response = self.session.get(SETTINGS.price_url, params=params, timeout=SETTINGS.request_timeout_seconds)
        response.raise_for_status()
        rows: List[Any] = response.json()
        candles: List[Candle] = []
        for row in rows:
            candles.append(Candle(open_time_ms=int(row[0]), open=float(row[1]), high=float(row[2]), low=float(row[3]), close=float(row[4]), volume=float(row[5])))
        return candles
