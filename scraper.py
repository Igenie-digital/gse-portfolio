"""
GSE price fetcher using the Kwayisi GSE live API.
Primary:  https://dev.kwayisi.org/apis/gse/live  (JSON, no auth needed)
Fallback: requests session against gse.com.gh
"""

import re
import logging
from datetime import date

import database as db
import notifier

logger = logging.getLogger(__name__)

KWAYISI_URL = "https://dev.kwayisi.org/apis/gse/live"
GSE_URL     = "https://gse.com.gh/market-data/equities/"
GSE_HOME    = "https://gse.com.gh/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


# ── Layer 1: Kwayisi GSE live API ─────────────────────────────────────────────

def scrape_kwayisi() -> list[dict]:
    import requests

    resp = requests.get(KWAYISI_URL, headers=HEADERS, timeout=40)
    resp.raise_for_status()

    data = resp.json()  # list of {name, price, change, volume}
    results = []
    for item in data:
        ticker = str(item.get("name", "")).strip().upper()
        price  = float(item.get("price", 0))
        change = float(item.get("change", 0))
        volume = int(item.get("volume", 0))
        if ticker and price > 0:
            results.append({
                "ticker": ticker,
                "price":  price,
                "change": change,
                "pct":    round(change / (price - change) * 100, 2) if (price - change) > 0 else 0,
                "volume": volume,
            })

    if not results:
        raise ValueError("Kwayisi API returned empty data")
    return results


# ── Layer 2: GSE website session fallback ─────────────────────────────────────

def _parse_float(text: str) -> float:
    try:
        return float(re.sub(r"[^\d.\-]", "", str(text))) or 0.0
    except ValueError:
        return 0.0


def scrape_gse_session() -> list[dict]:
    import requests
    from bs4 import BeautifulSoup

    session = requests.Session()
    session.headers.update(HEADERS)
    try:
        session.get(GSE_HOME, timeout=15)
    except Exception:
        pass

    resp = session.get(GSE_URL, timeout=25)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []
    for table in soup.find_all("table"):
        for row in table.find_all("tr")[1:]:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            try:
                ticker = cells[0].get_text(strip=True).upper()
                price  = float(re.sub(r"[^\d.]", "", cells[2].get_text(strip=True).replace(",", "")))
                change = _parse_float(cells[3].get_text(strip=True)) if len(cells) > 3 else 0
                pct    = _parse_float(cells[4].get_text(strip=True).replace("%", "")) if len(cells) > 4 else 0
                if ticker and price > 0:
                    results.append({"ticker": ticker, "price": price, "change": change, "pct": pct, "volume": 0})
            except (ValueError, IndexError):
                continue

    if not results:
        raise ValueError("GSE page loaded but no price table found")
    return results


# ── Main job ──────────────────────────────────────────────────────────────────

def run_scrape() -> dict:
    today = date.today().isoformat()
    known_tickers = {row["ticker"] for row in db.get_all_stocks()}
    results = []
    method = "unknown"
    errors = []

    for name, fn in [
        ("kwayisi", scrape_kwayisi),
        ("gse-session", scrape_gse_session),
    ]:
        try:
            rows = fn()
            if rows:
                results = rows
                method = name
                logger.info("%s returned %d rows", name, len(rows))
                break
        except Exception as e:
            errors.append(f"{name}: {e}")
            logger.warning("%s failed: %s", name, e)

    if not results:
        msg = "All scrapers failed — " + " | ".join(errors)
        db.log_scrape("error", msg, 0)
        return {"status": "error", "message": msg, "updated": 0}

    updated = 0
    for item in results:
        if item["ticker"] not in known_tickers:
            db.ensure_stock_exists(item["ticker"])  # auto-add new GSE listings
            logger.info("Auto-added new ticker: %s", item["ticker"])
        db.upsert_price(item["ticker"], today, item["price"], item["change"], item["pct"])
        updated += 1

    msg = f"Updated {updated} stock prices via {method} for {today}"
    db.log_scrape("ok", msg, updated)
    logger.info(msg)

    # Build ticker→price map and check active alerts
    price_map = {item["ticker"]: item["price"] for item in results}
    _check_alerts(price_map)

    return {"status": "ok", "message": msg, "updated": updated}


def _check_alerts(price_map: dict):
    alerts = db.get_active_alerts()
    if not alerts:
        return
    stocks = {r["ticker"]: r["name"] for r in db.get_all_stocks()}
    for alert in alerts:
        ticker  = alert["ticker"]
        current = price_map.get(ticker)
        if current is None:
            continue
        limit   = alert["limit_price"]
        cond    = alert["condition"]
        hit     = (cond == "above" and current >= limit) or \
                  (cond == "below" and current <= limit)
        if hit:
            db.trigger_alert(alert["id"])
            logger.info("Alert triggered: %s %s GHS %.4f (current GHS %.4f)",
                        ticker, cond, limit, current)
            notifier.send_price_alert(
                to_email=alert["email"] or alert["user_email"] or "",
                ticker=ticker,
                name=stocks.get(ticker, ticker),
                condition=cond,
                limit_price=limit,
                current_price=current,
            )


# ── Scheduler ─────────────────────────────────────────────────────────────────

def start_scheduler():
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler()

    # 08:00, 11:00, 14:00, 17:00 Mon–Fri Ghana time (UTC+0) — every ~3 hours
    scheduler.add_job(
        run_scrape,
        trigger="cron",
        day_of_week="mon-fri",
        hour="8,11,14,17",
        minute=0,
        id="gse_scrape",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started — runs at 08:00, 11:00, 14:00, 17:00 UTC Mon–Fri")
    return scheduler
