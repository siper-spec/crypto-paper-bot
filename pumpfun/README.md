# Pump.fun launch feed (read-only)

Connects to PumpPortal's public WebSocket with `subscribeNewToken` and records launches to SQLite.

**No wallet / API key / live trading.** The `candidate` flag indicates telemetry completeness only, **not** a profitable trading signal.

Run:
```bash
pip install -r pumpfun/requirements.txt
python pumpfun/collector.py
```
On Railway, configure the service start command to `pip install -r pumpfun/requirements.txt && python pumpfun/collector.py`. Attach a persistent volume at `/data`, set `PUMPFUN_DB=/data/launches.sqlite3`; without a volume, records may disappear after redeployment.

Keep all private keys and API keys outside GitHub, logs and chat. Previously exposed credentials must be replaced.

Next stage: authenticated trade-event feed and wallet/concentration filters; this phase does not produce a P&L.
