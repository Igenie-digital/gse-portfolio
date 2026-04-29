"""
Run this on your local Windows machine (in Ghana).
It fetches live GSE prices from Kwayisi and pushes them to your hosted app.

Schedule with Windows Task Scheduler to run every 3 hours on weekdays.
"""

import sys
import json
import logging
import requests
from datetime import datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

# ── Config — update these two values ─────────────────────────────────────────
APP_URL     = "https://gse-portfolio.onrender.com"   # your Render URL
PUSH_API_KEY = "REPLACE_WITH_YOUR_KEY"               # set same key in Render env vars
# ─────────────────────────────────────────────────────────────────────────────

KWAYISI_URL = "https://dev.kwayisi.org/apis/gse/live"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


def fetch_prices():
    resp = requests.get(KWAYISI_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    prices = []
    for item in data:
        ticker = str(item.get("name", "")).strip().upper()
        price  = float(item.get("price", 0))
        change = float(item.get("change", 0))
        pct    = round(change / (price - change) * 100, 2) if (price - change) > 0 else 0
        if ticker and price > 0:
            prices.append({"ticker": ticker, "price": price, "change": change, "pct": pct})
    return prices


def push(prices):
    url  = f"{APP_URL.rstrip('/')}/api/prices/push"
    body = {"api_key": PUSH_API_KEY, "prices": prices}
    resp = requests.post(url, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    logger.info("Fetching GSE prices from Kwayisi...")
    try:
        prices = fetch_prices()
        logger.info("Fetched %d prices", len(prices))
    except Exception as e:
        logger.error("Failed to fetch prices: %s", e)
        sys.exit(1)

    logger.info("Pushing to %s...", APP_URL)
    try:
        result = push(prices)
        logger.info("Done — %s", result)
    except Exception as e:
        logger.error("Failed to push: %s", e)
        sys.exit(1)
