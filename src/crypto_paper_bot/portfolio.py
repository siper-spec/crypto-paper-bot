
from __future__ import annotations
import json
from dataclasses import asdict
from pathlib import Path
import pandas as pd
from .config import SETTINGS
from .models import PortfolioState, Position, TradeRecord
class PortfolioManager:
    def __init__(self) -> None:
        self.state_path = Path(SETTINGS.output_state_path)
        self.trade_log_path = Path(SETTINGS.trade_log_path)
        self.equity_log_path = Path(SETTINGS.equity_log_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.trade_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.equity_log_path.parent.mkdir(parents=True, exist_ok=True)
    def load_state(self) -> PortfolioState:
        if not self.state_path.exists():
            return PortfolioState(cash_eur=SETTINGS.starting_balance_eur)
        payload = json.loads(self.state_path.read_text())
        position_payload = payload.get("position")
        position = Position(**position_payload) if position_payload else None
        return PortfolioState(cash_eur=float(payload["cash_eur"]), position=position, realized_pnl_eur=float(payload.get("realized_pnl_eur", 0.0)), trade_count=int(payload.get("trade_count", 0)), wins=int(payload.get("wins", 0)), losses=int(payload.get("losses", 0)), last_action=str(payload.get("last_action", "INIT")))
    def save_state(self, state: PortfolioState) -> None:
        self.state_path.write_text(json.dumps(asdict(state), indent=2))
    def append_trade(self, record: TradeRecord) -> None:
        row = pd.DataFrame([asdict(record)])
        if self.trade_log_path.exists():
            row.to_csv(self.trade_log_path, mode="a", header=False, index=False)
        else:
            row.to_csv(self.trade_log_path, index=False)
    def append_equity(self, timestamp_ms: int, price: float, state: PortfolioState) -> None:
        equity = state.cash_eur
        if state.position is not None:
            equity += state.position.quantity * price
        row = pd.DataFrame([{"timestamp_ms": timestamp_ms, "price": price, "cash_eur": state.cash_eur, "position_qty": state.position.quantity if state.position else 0.0, "equity_eur": equity, "realized_pnl_eur": state.realized_pnl_eur, "trade_count": state.trade_count, "wins": state.wins, "losses": state.losses, "last_action": state.last_action}])
        if self.equity_log_path.exists():
            row.to_csv(self.equity_log_path, mode="a", header=False, index=False)
        else:
            row.to_csv(self.equity_log_path, index=False)
    def execute_buy(self, state: PortfolioState, price: float, timestamp_ms: int, reason: str):
        cash_to_use = state.cash_eur * SETTINGS.position_size_fraction
        fee = cash_to_use * SETTINGS.fee_rate
        net_cash = max(0.0, cash_to_use - fee)
        qty = net_cash / price if price > 0 else 0.0
        position = Position(symbol=SETTINGS.symbol, entry_price=price, quantity=qty, entry_time_ms=timestamp_ms, stop_loss_price=price * (1.0 - SETTINGS.stop_loss_pct), take_profit_price=price * (1.0 + SETTINGS.take_profit_pct))
        state.cash_eur -= cash_to_use
        state.position = position
        state.trade_count += 1
        state.last_action = "BUY"
        record = TradeRecord(side="BUY", symbol=SETTINGS.symbol, price=price, quantity=qty, timestamp_ms=timestamp_ms, fee_paid=fee, pnl_eur=0.0, reason=reason)
        return state, record
    def execute_sell(self, state: PortfolioState, price: float, timestamp_ms: int, reason: str):
        if state.position is None:
            raise ValueError("No open position to sell")
        position = state.position
        gross_value = position.quantity * price
        fee = gross_value * SETTINGS.fee_rate
        net_value = gross_value - fee
        entry_gross = position.quantity * position.entry_price
        entry_fee = entry_gross * SETTINGS.fee_rate
        pnl = net_value - (entry_gross + entry_fee)
        state.cash_eur += net_value
        state.realized_pnl_eur += pnl
        if pnl >= 0:
            state.wins += 1
        else:
            state.losses += 1
        state.position = None
        state.last_action = "SELL"
        record = TradeRecord(side="SELL", symbol=SETTINGS.symbol, price=price, quantity=position.quantity, timestamp_ms=timestamp_ms, fee_paid=fee, pnl_eur=pnl, reason=reason)
        return state, record
