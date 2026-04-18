
# Crypto Paper Bot

Paper-trading crypto bot for fast testing with an imaginary starting balance of 100 EUR.

## What it does
- pulls Binance 1m candles
- computes EMA(9), EMA(21), RSI(14), and short momentum
- buys only when momentum and trend align
- uses a simulated stop loss and take profit
- logs trades and equity over time
- can send Telegram alerts

## Important
- this is paper trading only
- it does not place real trades
- it is not a guaranteed profitable strategy
- it is intended for a short test window of a few hours

## Telegram
Yes, you can use the same Telegram bot token and the same chat ID.

## Run
python -m src.crypto_paper_bot.alert_bot
