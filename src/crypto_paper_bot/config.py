from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _get_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return float(value)


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    price_url: str = os.getenv(
        "PRICE_URL",
        "https://api.exchange.coinbase.com/products",
    )
    request_timeout_seconds: int = _get_int("REQUEST_TIMEOUT_SECONDS", 20)

    symbol: str = os.getenv("SYMBOL", "BTC-USD")
    interval_seconds: int = _get_int("INTERVAL_SECONDS", 60)
    candle_limit: int = _get_int("CANDLE_LIMIT", 250)
    loop_interval_seconds: int = _get_int("LOOP_INTERVAL_SECONDS", 60)

    starting_balance_eur: float = _get_float("STARTING_BALANCE_EUR", 100.0)
    position_size_fraction: float = _get_float("POSITION_SIZE_FRACTION", 0.95)
    fee_rate: float = _get_float("FEE_RATE", 0.001)
    stop_loss_pct: float = _get_float("STOP_LOSS_PCT", 0.008)
    take_profit_pct: float = _get_float("TAKE_PROFIT_PCT", 0.012)
    max_hold_minutes: int = _get_int("MAX_HOLD_MINUTES", 90)

    ema_fast: int = _get_int("EMA_FAST", 9)
    ema_slow: int = _get_int("EMA_SLOW", 21)
    rsi_period: int = _get_int("RSI_PERIOD", 14)
    min_rsi_for_entry: float = _get_float("MIN_RSI_FOR_ENTRY", 53.0)
    max_rsi_for_entry: float = _get_float("MAX_RSI_FOR_ENTRY", 72.0)
    min_momentum_pct: float = _get_float("MIN_MOMENTUM_PCT", 0.0015)

    output_state_path: str = os.getenv("OUTPUT_STATE_PATH", "data/portfolio_state.json")
    trade_log_path: str = os.getenv("TRADE_LOG_PATH", "data/trades.csv")
    equity_log_path: str = os.getenv("EQUITY_LOG_PATH", "data/equity.csv")

    enable_telegram: bool = _get_bool("ENABLE_TELEGRAM", False)
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")


SETTINGS = Settings()
