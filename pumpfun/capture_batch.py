"""Bounded read-only PumpPortal token-launch capture for GitHub Actions."""
import argparse
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import websocket

URL = "wss://pumpportal.fun/api/data"

def capture(seconds=600, dest="pumpfun-launches.jsonl"):
    if not 1 <= seconds <= 3300:
        raise ValueError("seconds must be between 1 and 3300")
    path = Path(dest)
    path.parent.mkdir(parents=True, exist_ok=True)
    end = time.monotonic() + seconds
    counts = Counter()
    retries = 0
    last_error = None
    with path.open("w", encoding="utf-8") as out:
        while time.monotonic() < end:
            ws = None
            try:
                ws = websocket.create_connection(URL, timeout=8)
                ws.send(json.dumps({"method": "subscribeNewToken"}))
                retries = 0
                while time.monotonic() < end:
                    try:
                        ws.settimeout(min(5, max(0.1, end - time.monotonic())))
                        raw = ws.recv()
                    except websocket.WebSocketTimeoutException:
                        continue
                    if not raw:
                        break
                    try:
                        evt = json.loads(raw)
                    except (TypeError, ValueError):
                        counts["bad_json"] += 1
                        continue
                    if not isinstance(evt, dict) or not evt.get("mint"):
                        counts["other_messages"] += 1
                        continue
                    captured = {
                        "received_at": datetime.now(timezone.utc).isoformat(),
                        "mint": evt.get("mint"),
                        "symbol": evt.get("symbol"),
                        "name": evt.get("name"),
                        "creator": evt.get("traderPublicKey"),
                        "market_cap_sol": evt.get("marketCapSol"),
                        "initial_buy": evt.get("initialBuy"),
                        "sol_amount": evt.get("solAmount"),
                        "raw": evt,
                    }
                    out.write(json.dumps(captured, separators=(",", ":")) + "\n")
                    out.flush()
                    counts["launches"] += 1
            except (OSError, websocket.WebSocketException, ValueError) as e:
                last_error = str(e)[:200]
                counts["disconnects"] += 1
                retries += 1
                time.sleep(min(15, 2 ** min(retries, 4), max(0, end - time.monotonic())))
            finally:
                if ws:
                    try:
                        ws.close()
                    except Exception:
                        pass
    summary = {
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": seconds,
        "counts": dict(counts),
        "last_error": last_error,
        "source": "pumpportal-new-token-free",
        "status": "ok" if counts["launches"] else "empty_or_unavailable",
        "note": "Not a backtest; trade history and exits are not collected."
    }
    path.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    if not counts["launches"]:
        raise RuntimeError("No launches received; check PumpPortal connectivity and logs.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, default=int(os.getenv("CAPTURE_SECONDS", "600")))
    parser.add_argument("--out", default=os.getenv("CAPTURE_OUT", "pumpfun-launches.jsonl"))
    a = parser.parse_args()
    capture(a.seconds, a.out)
