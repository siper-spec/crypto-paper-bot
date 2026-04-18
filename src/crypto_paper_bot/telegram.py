
from __future__ import annotations
import requests
from .config import SETTINGS
from .models import PortfolioState, StrategyDecision
class TelegramNotifier:
    def __init__(self) -> None:
        self.enabled = bool(SETTINGS.enable_telegram and SETTINGS.telegram_bot_token and SETTINGS.telegram_chat_id)
    def send_text(self, text: str) -> bool:
        if not self.enabled:
            return False
        url = f"https://api.telegram.org/bot{SETTINGS.telegram_bot_token}/sendMessage"
        payload = {"chat_id": SETTINGS.telegram_chat_id, "text": text}
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        return True
    def send_decision(self, decision: StrategyDecision, state: PortfolioState) -> bool:
        equity = state.cash_eur
        if state.position is not None:
            equity += state.position.quantity * decision.price
        text = (
            f"📊 Crypto paper bot\n"
            f"Symbol: {SETTINGS.symbol}\n"
            f"Action: {decision.action}\n"
            f"Reason: {decision.reason}\n"
            f"Price: {decision.price:.2f}\n"
            f"EMA fast: {decision.indicators.ema_fast:.2f}\n"
            f"EMA slow: {decision.indicators.ema_slow:.2f}\n"
            f"RSI: {decision.indicators.rsi:.2f}\n"
            f"Momentum: {decision.indicators.momentum_pct:.4f}\n"
            f"Cash: {state.cash_eur:.2f}€\n"
            f"Equity: {equity:.2f}€"
        )
        return self.send_text(text)
