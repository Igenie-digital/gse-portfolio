import logging
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import database as db
import scraper
import importer
import auth

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scheduler
    db.init_db()
    scheduler = scraper.start_scheduler()
    logger.info("App started — database initialised")
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(title="GSE Portfolio Tracker", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def _fmt_ghs(value):
    return f"GHS {value:,.2f}"

def _sign(value):
    return f"+{value:.2f}" if value >= 0 else f"{value:.2f}"

def _sign_pct(value):
    arrow = "▲" if value >= 0 else "▼"
    return f"{arrow} {abs(value):.1f}%"

templates.env.filters["ghs"]      = _fmt_ghs
templates.env.filters["sign"]     = _sign
templates.env.filters["sign_pct"] = _sign_pct


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _get_user(request: Request):
    token = request.cookies.get("session")
    if not token:
        return None
    return db.get_session_user(token)


def _login_redirect():
    return RedirectResponse("/login", status_code=302)


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    if _get_user(request):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


@app.post("/login")
async def login(
    request:  Request,
    email:    str = Form(...),
    password: str = Form(...),
):
    user = db.get_user_by_email(email)
    if not user or not auth.verify_password(password, user["password_hash"]):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid email or password.",
        }, status_code=401)

    token = auth.new_token()
    db.create_session(token, user["id"], auth.token_expiry())

    response = RedirectResponse("/", status_code=302)
    response.set_cookie("session", token, httponly=True, max_age=60*60*24*30, samesite="lax")
    return response


@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request, error: str = ""):
    if _get_user(request):
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("signup.html", {"request": request, "error": error})


@app.post("/signup")
async def signup(
    request:  Request,
    name:     str = Form(...),
    email:    str = Form(...),
    password: str = Form(...),
    confirm:  str = Form(...),
):
    if len(password) < 8:
        return templates.TemplateResponse("signup.html", {
            "request": request, "error": "Password must be at least 8 characters.",
            "name": name, "email": email,
        }, status_code=400)
    if password != confirm:
        return templates.TemplateResponse("signup.html", {
            "request": request, "error": "Passwords do not match.",
            "name": name, "email": email,
        }, status_code=400)
    if db.get_user_by_email(email):
        return templates.TemplateResponse("signup.html", {
            "request": request, "error": "An account with that email already exists.",
            "name": name, "email": email,
        }, status_code=400)

    db.create_user(name, email, auth.hash_password(password))
    user = db.get_user_by_email(email)

    token = auth.new_token()
    db.create_session(token, user["id"], auth.token_expiry())

    response = RedirectResponse("/", status_code=302)
    response.set_cookie("session", token, httponly=True, max_age=60*60*24*30, samesite="lax")
    return response


@app.post("/logout")
async def logout(request: Request):
    token = request.cookies.get("session")
    if token:
        db.delete_session(token)
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie("session")
    return response


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = _get_user(request)
    if not user:
        return _login_redirect()
    portfolio   = db.get_portfolio(user["id"])
    summary     = db.get_portfolio_summary(portfolio)
    last_scrape = db.get_last_scrape()
    sorted_by_roi    = sorted(portfolio, key=lambda h: h["gain_loss_pct"], reverse=True)
    all_stocks       = db.get_all_stocks()
    unclassified_count = sum(1 for s in all_stocks if s["category"] == "Unclassified")
    return templates.TemplateResponse("dashboard.html", {
        "request":            request,
        "user":               user,
        "portfolio":          portfolio,
        "summary":            summary,
        "top_performers":     sorted_by_roi,
        "last_scrape":        last_scrape,
        "today":              date.today().isoformat(),
        "all_stocks":         all_stocks,
        "unclassified_count": unclassified_count,
    })


# ── Trades ────────────────────────────────────────────────────────────────────

@app.get("/trades", response_class=HTMLResponse)
async def trades_page(request: Request, imported: int = 0, skipped: int = 0):
    user = _get_user(request)
    if not user:
        return _login_redirect()
    trades = db.get_all_trades(user["id"])
    market = db.get_latest_prices()
    stocks = market if market else db.get_all_stocks()
    return templates.TemplateResponse("trades.html", {
        "request":  request,
        "user":     user,
        "trades":   trades,
        "stocks":   stocks,
        "today":    date.today().isoformat(),
        "imported": imported,
        "skipped":  skipped,
    })


@app.post("/trades/add")
async def add_trade(
    request:    Request,
    order_date: str   = Form(...),
    ticker:     str   = Form(...),
    units:      float = Form(...),
    price:      float = Form(...),
    amount:     float = Form(...),
    broker:     str   = Form(""),
):
    user = _get_user(request)
    if not user:
        return _login_redirect()
    ticker = ticker.upper().strip()
    try:
        db.add_trade(order_date, ticker, units, price, amount, broker, user["id"])
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse("/trades", status_code=303)


@app.post("/trades/delete/{trade_id}")
async def delete_trade(trade_id: int, request: Request):
    user = _get_user(request)
    if not user:
        return _login_redirect()
    db.delete_trade(trade_id, user["id"])
    return RedirectResponse("/trades", status_code=303)


@app.post("/trades/upload")
async def upload_trades_file(request: Request, file: UploadFile = File(...)):
    user = _get_user(request)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    try:
        content = await file.read()
        result  = importer.store_upload(content, file.filename or "upload")
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/trades/import")
async def import_trades(request: Request):
    user = _get_user(request)
    if not user:
        return _login_redirect()
    form = await request.form()
    upload_id = form.get("upload_id", "")
    mapping = {
        "order_date": form.get("map_order_date", ""),
        "ticker":     form.get("map_ticker",     ""),
        "units":      form.get("map_units",      ""),
        "price":      form.get("map_price",      ""),
        "amount":     form.get("map_amount",     ""),
        "broker":     form.get("map_broker",     ""),
    }
    try:
        result = importer.do_import(upload_id, mapping, user["id"])
        return RedirectResponse(
            f"/trades?imported={result['imported']}&skipped={len(result['errors'])}",
            status_code=303
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Market Board ──────────────────────────────────────────────────────────────

@app.get("/market", response_class=HTMLResponse)
async def market_page(request: Request):
    user = _get_user(request)
    if not user:
        return _login_redirect()
    prices      = db.get_latest_prices()
    last_scrape = db.get_last_scrape()
    alerts      = db.get_all_alerts(user["id"])
    return templates.TemplateResponse("market.html", {
        "request":    request,
        "user":       user,
        "prices":     prices,
        "last_scrape": last_scrape,
        "alerts":     alerts,
    })


# ── Price Alerts ──────────────────────────────────────────────────────────────

@app.post("/alerts/add")
async def add_alert(
    request:     Request,
    ticker:      str   = Form(...),
    condition:   str   = Form(...),
    limit_price: float = Form(...),
    email:       str   = Form(""),
):
    user = _get_user(request)
    if not user:
        return _login_redirect()
    db.add_alert(ticker.upper().strip(), condition, limit_price, email, user["id"])
    return RedirectResponse("/market", status_code=303)


@app.post("/alerts/delete/{alert_id}")
async def delete_alert(alert_id: int, request: Request):
    user = _get_user(request)
    if not user:
        return _login_redirect()
    db.delete_alert(alert_id, user["id"])
    return RedirectResponse("/market", status_code=303)


@app.post("/alerts/dismiss/{alert_id}")
async def dismiss_alert(alert_id: int, request: Request):
    user = _get_user(request)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    db.dismiss_alert(alert_id)
    return JSONResponse({"ok": True})


@app.get("/api/alerts/triggered")
async def triggered_alerts(request: Request):
    user = _get_user(request)
    if not user:
        return JSONResponse([])
    rows = db.get_undismissed_triggered(user["id"])
    return JSONResponse([
        {
            "id":           r["id"],
            "ticker":       r["ticker"],
            "name":         r["name"],
            "condition":    r["condition"],
            "limit_price":  r["limit_price"],
            "triggered_at": r["triggered_at"],
        }
        for r in rows
    ])


# ── Price history ─────────────────────────────────────────────────────────────

@app.get("/api/price-history/{ticker}")
async def price_history(ticker: str, days: int = 90):
    rows = db.get_price_history(ticker.upper(), days)
    return JSONResponse({
        "ticker": ticker,
        "labels": [r["date"] for r in reversed(rows)],
        "prices": [r["price"] for r in reversed(rows)],
    })


# ── Manual price update ───────────────────────────────────────────────────────

@app.post("/prices/manual")
async def manual_price(request: Request, ticker: str = Form(...), price: float = Form(...)):
    user = _get_user(request)
    if not user:
        return _login_redirect()
    ticker = ticker.upper().strip()
    today  = date.today().isoformat()
    db.upsert_price(ticker, today, price)
    return RedirectResponse("/market", status_code=303)


# ── Trigger scrape on demand ──────────────────────────────────────────────────

@app.post("/api/scrape")
async def trigger_scrape(request: Request):
    user = _get_user(request)
    if not user:
        return JSONResponse({"status": "error", "message": "Not authenticated"}, status_code=401)
    result = scraper.run_scrape()
    return JSONResponse(result)


# ── Stock category update ─────────────────────────────────────────────────────

@app.post("/stocks/category")
async def update_category(request: Request, ticker: str = Form(...), category: str = Form(...)):
    user = _get_user(request)
    if not user:
        return _login_redirect()
    with db.get_conn() as conn:
        conn.execute("UPDATE stocks SET category=? WHERE ticker=?", (category, ticker.upper()))
    return RedirectResponse("/market", status_code=303)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)
