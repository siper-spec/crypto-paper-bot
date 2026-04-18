from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, List

import requests

from .config import SETTINGS
from .models import Candle


class CoinbaseMarketDataClient:
    def __init__(self) -> None:
        self.session = requests.Session()

    def fetch_candles(self) -> List[Candle]:
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(seconds=SETTINGS.interval_seconds * SETTINGS.candle_limit)

        url = f"{SETTINGS.price_url}/{SETTINGS.symbol}/candles"
        params = {
            "granularity": SETTINGS.interval_seconds,
            "start": start_time.isoformat(),
            "end": end_time.isoformat(),
        }

        response = self.session.get(
            url,
            params=params,
            timeout=SETTINGS.request_timeout_seconds,
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()

        rows: List[Any] = response.json()
        candles: List[Candle] = []

        # Coinbase format:
        # [time, low, high, open, close, volume]
        for row in rows:
            candles.append(
                Candle(
                    open_time_ms=int(row[0]) * 1000,
                    open=float(row[3]),
                    high=float(row[2]),
                    low=float(row[1]),
                    close=float(row[4]),
                    volume=float(row[5]),
                )
            )

        candles.sort(key=lambda c: c.open_time_ms)
        return candles
