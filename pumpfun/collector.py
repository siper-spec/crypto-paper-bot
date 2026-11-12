"""Read-only PumpPortal launch collector; never signs transactions."""
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
import websocket

URL = "wss://pumpportal.fun/api/data"
DB_PATH = Path(os.getenv("PUMPFUN_DB", "pumpfun_events.sqlite3"))
log = logging.getLogger("pumpfun")

def db_open():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""CREATE TABLE IF NOT EXISTS launches(
        mint TEXT PRIMARY KEY, seen_at TEXT NOT NULL, symbol TEXT, name TEXT,
        creator TEXT, market_cap_sol REAL, candidate INTEGER,
        reason TEXT, raw_json TEXT NOT NULL)""")
    db.commit()
    return db

def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def classify(data):
    if not isinstance(data.get("mint"), str) or not data["mint"]:
        return False, "no_mint"
    if number(data.get("marketCapSol")) is None:
        return False, "no_cap"
    return True, "watch_only_not_buy_signal"

def record(db, data):
    if not isinstance(data, dict) or not data.get("mint"):
        return False
    watch, reason = classify(data)
    db.execute("""INSERT OR IGNORE INTO launches
        (mint,seen_at,symbol,name,creator,market_cap_sol,candidate,reason,raw_json)
        VALUES(?,?,?,?,?,?,?,?,?)""",
        (data["mint"], datetime.now(timezone.utc).isoformat(),
         data.get("symbol"), data.get("name"), data.get("traderPublicKey"),
         number(data.get("marketCapSol")), int(watch), reason, json.dumps(data)))
    db.commit()
    return db.execute("SELECT changes()").fetchone()[0] > 0

def run():
    db = db_open()
    retries = 0
    while True:
        try:
            ws = websocket.create_connection(URL, timeout=30)
            ws.send(json.dumps({"method": "subscribeNewToken"}))
            retries = 0
            log.info("Subscribed to new Pump.fun launches")
            while True:
                event = json.loads(ws.recv())
                if record(db, event):
                    log.info("launch mint=%s symbol=%s", event.get("mint"), event.get("symbol"))
        except (OSError, ValueError, websocket.WebSocketException) as exc:
            retries += 1
            delay = min(60, 2 ** min(retries, 6))
            log.warning("Disconnected: %s; retry in %ss", str(exc)[:200], delay)
            time.sleep(delay)

if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    run()
