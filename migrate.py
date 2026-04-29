"""
Run this ONCE to import your existing trades and seed initial prices from your sheet.
Usage:  python migrate.py
"""

import database as db
from datetime import date

def run():
    db.init_db()
    print("Database initialised.")

    # ── Your 20 existing trades (from Google Sheet) ──────────────────────────
    trades = [
        ("2026-02-26", "MTNGH", 17.47, 5.58,  100.00,  "Blackstar"),
        ("2026-03-02", "MTNGH", 84.64, 5.76,  500.00,  "Blackstar"),
        ("2026-03-05", "GGBL",  15.14, 16.10, 250.00,  "Blackstar"),
        ("2026-03-10", "CAL",  110.80, 0.88,  100.00,  "Blackstar"),
        ("2026-03-11", "ETI",   84.05, 1.74,  150.00,  "Blackstar"),
        ("2026-03-13", "MTNGH", 31.10, 6.27,  200.00,  "Blackstar"),
        ("2026-03-16", "SIC",   78.50, 6.21,  500.00,  "Blackstar"),
        ("2026-03-16", "EGL",   40.09, 12.16, 500.00,  "Blackstar"),
        ("2026-03-18", "ETI",   59.45, 2.46,  150.00,  "Blackstar"),
        ("2026-03-20", "SIC",   70.00, 5.59,  401.08,  "IC Wealth"),
        ("2026-03-24", "FML",   35.37, 13.79, 500.00,  "Blackstar"),
        ("2026-03-30", "CAL",  100.00, 0.75,   76.87,  "IC Wealth"),
        ("2026-03-31", "MTNGH", 27.09, 5.40,  150.00,  "Blackstar"),
        ("2026-03-31", "SIC",  105.00, 3.50,  376.69,  "IC Wealth"),
        ("2026-03-31", "SIC",  100.00, 3.50,  358.74,  "IC Wealth"),
        ("2026-04-01", "MTNGH",100.00, 5.00,  512.50,  "IC Wealth"),
        ("2026-04-10", "GCB",   18.60, 25.96, 495.00,  "Blackstar"),
        ("2026-04-14", "GCB",   23.00, 25.85, 607.92,  "IC Wealth"),
        ("2026-04-20", "TOTAL", 18.00, 34.57, 622.26,  "IC Wealth"),
        ("2026-04-21", "TOTAL",  9.98, 34.57, 354.00,  "Blackstar"),
    ]

    added = 0
    for (order_date, ticker, units, price, amount, broker) in trades:
        db.add_trade(order_date, ticker, units, price, amount, broker)
        added += 1
    print(f"Imported {added} trades.")

    # ── Seed latest prices from your sheet (as of 2026-04-22) ────────────────
    seed_prices = [
        ("ACCESS",  30.65), ("ADB",   5.06), ("CAL",   0.90),
        ("EGH",    48.90), ("EGL",  11.20), ("ETI",   2.31),
        ("GCB",    42.27), ("RBGH",  4.72), ("SCB",  71.38),
        ("SCBPREF", 0.90), ("SOGEGH",6.29), ("GLD", 502.89),
        ("ALLGH",   7.20), ("CLYD",  1.44), ("IIL",   0.05),
        ("SIC",     4.85), ("ASG",   8.89), ("BOPP", 87.00),
        ("CPC",     0.12), ("FAB",   7.97), ("FML",  12.50),
        ("GGBL",   15.30), ("MAC",   5.20), ("TBL",   1.20),
        ("AGA",    37.00), ("GOIL",  8.00), ("TLW",  11.92),
        ("TOTAL",  34.55), ("AADS",  0.42), ("CMLT",  0.14),
        ("HORDS",   0.10), ("MMH",   0.10), ("SAMBA", 0.55),
        ("DASPHARMA",0.41),("UNIL", 28.46), ("DIGICUT",0.09),
        ("MTNGH",   6.52),
    ]

    price_date = "2026-04-22"
    for ticker, price in seed_prices:
        db.upsert_price(ticker, price_date, price)
    print(f"Seeded {len(seed_prices)} prices for {price_date}.")
    print("\nMigration complete. Run: python app.py")

if __name__ == "__main__":
    run()
