
from __future__ import annotations
import time
from .config import SETTINGS
from .runner import run_once
def main() -> None:
    print("Starting crypto paper bot loop...")
    print(f"Loop interval: {SETTINGS.loop_interval_seconds} seconds")
    while True:
        try:
            run_once(send_alerts=True)
        except KeyboardInterrupt:
            print("Stopped by user.")
            break
        except Exception as exc:
            print(f"Loop error: {exc}")
        time.sleep(SETTINGS.loop_interval_seconds)
if __name__ == "__main__":
    main()
