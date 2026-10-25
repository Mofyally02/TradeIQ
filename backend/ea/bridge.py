"""Forwards files written by TradeIQ_Journal (UseFileBridge=true) to the TradeIQ webhook.

Usage: python bridge.py <path to MQL5/Files> <webhook url>
"""
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def main() -> None:
    folder, url = Path(sys.argv[1]), sys.argv[2]
    print(f"Bridge watching {folder}", flush=True)
    while True:
        for path in sorted(folder.glob("tradeiq_out_*.json")):
            try:
                body = path.read_bytes()
                request = urllib.request.Request(
                    url, data=body, headers={"Content-Type": "application/json"}, method="POST"
                )
                with urllib.request.urlopen(request, timeout=30) as response:
                    print(path.name, response.status, flush=True)
                path.unlink()
            except urllib.error.HTTPError as error:
                print(path.name, "HTTP", error.code, flush=True)
                if error.code < 500:
                    path.unlink()
            except Exception as error:
                print(path.name, "retry:", error, flush=True)
                break
        time.sleep(2)


if __name__ == "__main__":
    main()
