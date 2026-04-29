import os
import sqlite3
from pathlib import Path
from datetime import date

_data_dir = os.getenv("DATA_DIR", str(Path(__file__).parent))
DB_PATH   = Path(_data_dir) / "portfolio.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            email         TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token      TEXT PRIMARY KEY,
            user_id    INTEGER NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS stocks (
            ticker    TEXT PRIMARY KEY,
            name      TEXT NOT NULL,
            sector    TEXT,
            category  TEXT DEFAULT 'Unclassified'
        );

        CREATE TABLE IF NOT EXISTS trades (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            order_date  TEXT NOT NULL,
            ticker      TEXT NOT NULL,
            units       REAL NOT NULL,
            price       REAL NOT NULL,
            amount      REAL NOT NULL,
            broker      TEXT,
            created_at  TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (ticker)  REFERENCES stocks(ticker),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS prices (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker     TEXT NOT NULL,
            date       TEXT NOT NULL,
            price      REAL NOT NULL,
            change     REAL DEFAULT 0,
            pct_change REAL DEFAULT 0,
            UNIQUE(ticker, date),
            FOREIGN KEY (ticker) REFERENCES stocks(ticker)
        );

        CREATE TABLE IF NOT EXISTS scrape_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ran_at          TEXT DEFAULT (datetime('now')),
            status          TEXT,
            message         TEXT,
            tickers_updated INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS price_alerts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER,
            ticker       TEXT NOT NULL,
            condition    TEXT NOT NULL CHECK(condition IN ('above','below')),
            limit_price  REAL NOT NULL,
            email        TEXT,
            active       INTEGER DEFAULT 1,
            triggered_at TEXT,
            dismissed    INTEGER DEFAULT 0,
            created_at   TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (ticker)   REFERENCES stocks(ticker),
            FOREIGN KEY (user_id)  REFERENCES users(id)
        );
        """)
        _migrate(conn)
        _seed_stocks(conn)


def _migrate(conn):
    """Add new columns to existing tables without dropping data."""
    migrations = [
        "ALTER TABLE trades       ADD COLUMN user_id INTEGER REFERENCES users(id)",
        "ALTER TABLE price_alerts ADD COLUMN user_id INTEGER REFERENCES users(id)",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
        except Exception:
            pass   # column already exists


def _seed_stocks(conn):
    gse_stocks = [
        ("ACCESS", "Access Bank Ghana Plc", "Banking", "Unclassified"),
        ("ADB",    "Agricultural Development Bank", "Banking", "Unclassified"),
        ("CAL",    "CAL Bank Plc", "Banking", "Value Stock"),
        ("EGH",    "Ecobank Ghana Limited", "Banking", "Unclassified"),
        ("EGL",    "Enterprise Group Limited", "Banking", "Growth Stock"),
        ("ETI",    "Ecobank Transactional Incorporation", "Banking", "Value Stock"),
        ("GCB",    "GCB Bank Ltd", "Banking", "Dividend Stock"),
        ("RBGH",   "Republic Bank Ghana Limited", "Banking", "Unclassified"),
        ("SCB",    "Standard Chartered Bank Ghana", "Banking", "Unclassified"),
        ("SCBPREF","SCB Preference Shares", "Banking", "Unclassified"),
        ("SOGEGH", "Societe Generale Ghana", "Banking", "Unclassified"),
        ("GLD",    "Gold ETF", "ETF", "Unclassified"),
        ("ALLGH",  "Allianz Insurance Ghana", "Insurance", "Unclassified"),
        ("CLYD",   "Clydestone Ghana Limited", "Insurance", "Unclassified"),
        ("IIL",    "Industrial Insurance Limited", "Insurance", "Unclassified"),
        ("SIC",    "SIC Insurance Company Limited", "Insurance", "Value Stock"),
        ("ASG",    "Aluworks Ghana Limited", "Manufacturing", "Unclassified"),
        ("BOPP",   "Benso Oil Palm Plantation", "Manufacturing", "Unclassified"),
        ("CPC",    "Camelot Printing & Packaging", "Manufacturing", "Unclassified"),
        ("FAB",    "First Atlantic Bank", "Manufacturing", "Unclassified"),
        ("FML",    "Fan Milk Limited", "Manufacturing", "Value Stock"),
        ("GGBL",   "Guinness Ghana Breweries Ltd", "Manufacturing", "Value Stock"),
        ("MAC",    "Mechanical Lloyd Company", "Manufacturing", "Unclassified"),
        ("TBL",    "Trust Bank Limited", "Manufacturing", "Unclassified"),
        ("AGA",    "AngloGold Ashanti", "Mining", "Unclassified"),
        ("GOIL",   "GOIL Company Limited", "Oil & Gas", "Unclassified"),
        ("TLW",    "Tullow Oil Plc", "Oil & Gas", "Unclassified"),
        ("TOTAL",  "Total Petroleum Ghana", "Oil & Gas", "Dividend Stock"),
        ("AADS",   "AADS Limited", "Other / SME", "Unclassified"),
        ("CMLT",   "Camelot Limited", "Other / SME", "Unclassified"),
        ("HORDS",  "Hords Limited", "Other / SME", "Unclassified"),
        ("MMH",    "Mega African Capital", "Other / SME", "Unclassified"),
        ("SAMBA",  "Samba Foods Limited", "Other / SME", "Unclassified"),
        ("DASPHARMA","DAS Pharma Limited", "Pharmaceuticals", "Unclassified"),
        ("UNIL",   "Unilever Ghana Limited", "Retail / FMCG", "Unclassified"),
        ("DIGICUT","Digicut Technologies", "Technology", "Unclassified"),
        ("MTNGH",  "MTN Ghana", "Telecom", "Dividend Stock"),
    ]
    conn.executemany(
        "INSERT OR IGNORE INTO stocks (ticker, name, sector, category) VALUES (?,?,?,?)",
        gse_stocks
    )


# ── Users & Sessions ──────────────────────────────────────────────────────────

def create_user(name: str, email: str, password_hash: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?,?,?)",
            (name.strip(), email.lower().strip(), password_hash)
        )


def get_user_by_email(email: str):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE email=?", (email.lower().strip(),)
        ).fetchone()


def get_user_by_id(user_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE id=?", (user_id,)
        ).fetchone()


def create_session(token: str, user_id: int, expires_at: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?,?,?)",
            (token, user_id, expires_at)
        )


def get_session_user(token: str):
    with get_conn() as conn:
        return conn.execute("""
            SELECT u.* FROM users u
            JOIN sessions s ON s.user_id = u.id
            WHERE s.token = ? AND s.expires_at > datetime('now')
        """, (token,)).fetchone()


def delete_session(token: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE token=?", (token,))


# ── Trades ────────────────────────────────────────────────────────────────────

def add_trade(order_date, ticker, units, price, amount, broker, user_id=None):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO trades (user_id, order_date, ticker, units, price, amount, broker) VALUES (?,?,?,?,?,?,?)",
            (user_id, order_date, ticker, float(units), float(price), float(amount), broker)
        )


def get_all_trades(user_id=None):
    with get_conn() as conn:
        return conn.execute("""
            SELECT t.id, t.order_date, t.ticker, s.name, t.units, t.price, t.amount, t.broker
            FROM trades t JOIN stocks s ON t.ticker = s.ticker
            WHERE t.user_id = ?
            ORDER BY t.order_date DESC, t.id DESC
        """, (user_id,)).fetchall()


def delete_trade(trade_id, user_id=None):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM trades WHERE id=? AND (user_id=? OR user_id IS NULL)",
            (trade_id, user_id)
        )


# ── Prices ────────────────────────────────────────────────────────────────────

def upsert_price(ticker, price_date, price, change=0, pct_change=0):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO prices (ticker, date, price, change, pct_change)
            VALUES (?,?,?,?,?)
            ON CONFLICT(ticker, date) DO UPDATE SET
                price=excluded.price,
                change=excluded.change,
                pct_change=excluded.pct_change
        """, (ticker, price_date, float(price), float(change), float(pct_change)))


def get_latest_prices():
    with get_conn() as conn:
        return conn.execute("""
            SELECT p.ticker, s.name, s.sector, p.price, p.change, p.pct_change, p.date
            FROM prices p
            JOIN stocks s ON p.ticker = s.ticker
            WHERE p.date = (SELECT MAX(date) FROM prices p2 WHERE p2.ticker = p.ticker)
            ORDER BY p.ticker
        """).fetchall()


def ensure_stock_exists(ticker: str, name: str = None, sector: str = None):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO stocks (ticker, name, sector, category) VALUES (?,?,?,?)",
            (ticker, name or ticker, sector or "Unclassified", "Unclassified")
        )


def get_price_history(ticker, days=90):
    with get_conn() as conn:
        return conn.execute("""
            SELECT date, price FROM prices
            WHERE ticker=?
            ORDER BY date DESC
            LIMIT ?
        """, (ticker, days)).fetchall()


def get_all_stocks():
    with get_conn() as conn:
        return conn.execute("SELECT * FROM stocks ORDER BY ticker").fetchall()


# ── Portfolio ─────────────────────────────────────────────────────────────────

def get_portfolio(user_id=None):
    with get_conn() as conn:
        holdings = conn.execute("""
            SELECT
                t.ticker,
                s.name,
                s.category,
                SUM(t.units)  AS shares,
                SUM(t.amount) AS total_cost,
                SUM(t.amount) / SUM(t.units) AS avg_cost
            FROM trades t
            JOIN stocks s ON t.ticker = s.ticker
            WHERE t.user_id = ?
            GROUP BY t.ticker
            ORDER BY s.category, t.ticker
        """, (user_id,)).fetchall()

        result = []
        for h in holdings:
            price_row = conn.execute("""
                SELECT price, date FROM prices
                WHERE ticker=? ORDER BY date DESC LIMIT 1
            """, (h["ticker"],)).fetchone()

            current_price = price_row["price"] if price_row else h["avg_cost"]
            price_date    = price_row["date"]   if price_row else "N/A"
            market_value  = current_price * h["shares"]
            gain_loss     = market_value - h["total_cost"]
            gain_loss_pct = (gain_loss / h["total_cost"]) * 100 if h["total_cost"] else 0

            result.append({
                "ticker":        h["ticker"],
                "name":          h["name"],
                "category":      h["category"],
                "shares":        round(h["shares"], 2),
                "total_cost":    round(h["total_cost"], 2),
                "avg_cost":      round(h["avg_cost"], 4),
                "current_price": round(current_price, 4),
                "market_value":  round(market_value, 2),
                "gain_loss":     round(gain_loss, 2),
                "gain_loss_pct": round(gain_loss_pct, 2),
                "price_date":    price_date,
            })
        return result


def get_portfolio_summary(portfolio):
    total_cost  = sum(h["total_cost"]   for h in portfolio)
    total_value = sum(h["market_value"] for h in portfolio)
    total_gl    = total_value - total_cost
    roi         = (total_gl / total_cost * 100) if total_cost else 0

    categories = {}
    for h in portfolio:
        cat = h["category"]
        if cat not in categories:
            categories[cat] = {"count": 0, "cost": 0, "value": 0}
        categories[cat]["count"] += 1
        categories[cat]["cost"]  += h["total_cost"]
        categories[cat]["value"] += h["market_value"]

    for cat in categories:
        c = categories[cat]
        c["weight"] = round(c["cost"] / total_cost * 100, 1) if total_cost else 0
        c["gl_pct"] = round((c["value"] - c["cost"]) / c["cost"] * 100, 1) if c["cost"] else 0
        c["cost"]   = round(c["cost"], 2)
        c["value"]  = round(c["value"], 2)

    for h in portfolio:
        h["weight"] = round(h["market_value"] / total_value * 100, 1) if total_value else 0

    return {
        "total_cost":  round(total_cost, 2),
        "total_value": round(total_value, 2),
        "total_gl":    round(total_gl, 2),
        "roi":         round(roi, 2),
        "categories":  categories,
    }


def log_scrape(status, message, tickers_updated=0):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO scrape_log (status, message, tickers_updated) VALUES (?,?,?)",
            (status, message, tickers_updated)
        )


def get_last_scrape():
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM scrape_log ORDER BY ran_at DESC LIMIT 1"
        ).fetchone()


# ── Price Alerts ──────────────────────────────────────────────────────────────

def add_alert(ticker: str, condition: str, limit_price: float,
              email: str = "", user_id=None):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO price_alerts (user_id, ticker, condition, limit_price, email) VALUES (?,?,?,?,?)",
            (user_id, ticker.upper(), condition, float(limit_price), email.strip())
        )


def get_all_alerts(user_id=None):
    with get_conn() as conn:
        return conn.execute("""
            SELECT a.*, s.name
            FROM price_alerts a
            JOIN stocks s ON a.ticker = s.ticker
            WHERE a.user_id = ?
            ORDER BY a.active DESC, a.created_at DESC
        """, (user_id,)).fetchall()


def get_active_alerts():
    """Used by the scraper — returns all active alerts with user email fallback."""
    with get_conn() as conn:
        return conn.execute("""
            SELECT a.*, s.name AS stock_name, u.email AS user_email
            FROM price_alerts a
            JOIN stocks s ON a.ticker = s.ticker
            LEFT JOIN users u ON a.user_id = u.id
            WHERE a.active = 1
        """).fetchall()


def trigger_alert(alert_id: int):
    with get_conn() as conn:
        conn.execute("""
            UPDATE price_alerts
            SET active=0, triggered_at=datetime('now'), dismissed=0
            WHERE id=?
        """, (alert_id,))


def dismiss_alert(alert_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE price_alerts SET dismissed=1 WHERE id=?", (alert_id,)
        )


def get_undismissed_triggered(user_id=None):
    with get_conn() as conn:
        return conn.execute("""
            SELECT a.*, s.name
            FROM price_alerts a
            JOIN stocks s ON a.ticker = s.ticker
            WHERE a.active=0 AND a.dismissed=0 AND a.user_id=?
            ORDER BY a.triggered_at DESC
        """, (user_id,)).fetchall()


def delete_alert(alert_id: int, user_id=None):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM price_alerts WHERE id=? AND user_id=?",
            (alert_id, user_id)
        )
