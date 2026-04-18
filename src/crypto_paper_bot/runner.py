from __future__ import annotations

from .config import SETTINGS
from .indicators import build_snapshot
from .market_data import CoinbaseMarketDataClient
from .portfolio import PortfolioManager
from .strategy import decide
from .telegram import TelegramNotifier


def run_once(send_alerts: bool = False) -> None:
    data_client = CoinbaseMarketDataClient()
    portfolio_manager = PortfolioManager()
    notifier = TelegramNotifier()

    candles = data_client.fetch_candles()
    if not candles:
        print("No candles returned")
        return

    snapshot = build_snapshot(
        candles,
        ema_fast_period=SETTINGS.ema_fast,
        ema_slow_period=SETTINGS.ema_slow,
        rsi_period=SETTINGS.rsi_period,
    )

    latest_time_ms = candles[-1].open_time_ms
    state = portfolio_manager.load_state()
    decision = decide(state, snapshot, latest_time_ms)

    if decision.action == "BUY" and state.position is None:
        state, record = portfolio_manager.execute_buy(
            state, decision.price, latest_time_ms, decision.reason
        )
        portfolio_manager.append_trade(record)
        print(
            f"BUY  | price={decision.price:.2f} | qty={record.quantity:.6f} | reason={decision.reason}"
        )
        if send_alerts:
            notifier.send_decision(decision, state)

    elif decision.action == "SELL" and state.position is not None:
        state, record = portfolio_manager.execute_sell(
            state, decision.price, latest_time_ms, decision.reason
        )
        portfolio_manager.append_trade(record)
        print(
            f"SELL | price={decision.price:.2f} | pnl={record.pnl_eur:.2f}€ | reason={decision.reason}"
        )
        if send_alerts:
            notifier.send_decision(decision, state)

    else:
        print(
            f"HOLD | price={decision.price:.2f} | "
            f"rsi={decision.indicators.rsi:.2f} | "
            f"ema_fast={decision.indicators.ema_fast:.2f} | "
            f"ema_slow={decision.indicators.ema_slow:.2f} | "
            f"{decision.reason}"
        )

    portfolio_manager.append_equity(latest_time_ms, decision.price, state)
    portfolio_manager.save_state(state)

    equity = state.cash_eur
    if state.position is not None:
        equity += state.position.quantity * decision.price

    print(
        f"State | cash={state.cash_eur:.2f}€ | "
        f"equity={equity:.2f}€ | "
        f"realized={state.realized_pnl_eur:.2f}€ | "
        f"wins={state.wins} | losses={state.losses}"
    )
