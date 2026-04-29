"""
File import helpers: parse CSV / XLSX, store temporarily, then map and save trades.
"""

import csv
import io
import re
import uuid
from datetime import datetime

# ── Temporary in-memory store ─────────────────────────────────────────────────
# { upload_id: {"columns": [...], "rows": [[...], ...]} }
_uploads: dict = {}

DATE_FORMATS = [
    "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y",
    "%m-%d-%Y", "%d-%m-%Y", "%Y/%m/%d",
    "%d %b %Y", "%d %B %Y", "%b %d, %Y",
    "%m/%d/%y", "%d/%m/%y", "%Y%m%d",
]


def _parse_date(s: str) -> str:
    s = str(s).strip().split(" ")[0]   # drop any time component
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date format: '{s}'")


def _parse_num(s) -> float:
    if s is None:
        return 0.0
    cleaned = re.sub(r"[^\d.\-]", "", str(s))
    return float(cleaned) if cleaned else 0.0


def _clean_rows(raw: list[list]) -> tuple[list[str], list[list[str]]]:
    """Split header row from data rows; skip fully empty rows."""
    if not raw:
        raise ValueError("File appears to be empty.")
    headers = [str(c).strip() for c in raw[0]]
    data = [
        [str(c).strip() for c in row]
        for row in raw[1:]
        if any(str(c).strip() for c in row)
    ]
    if not data:
        raise ValueError("No data rows found after the header.")
    return headers, data


# ── Parsers ───────────────────────────────────────────────────────────────────

def _parse_csv(file_bytes: bytes) -> list[list]:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = file_bytes.decode(encoding)
            reader = csv.reader(io.StringIO(text))
            rows = [r for r in reader if any(c.strip() for c in r)]
            return rows
        except UnicodeDecodeError:
            continue
    raise ValueError("Could not decode CSV file. Try saving as UTF-8.")


def _parse_excel(file_bytes: bytes) -> list[list]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb.active
    rows = []
    for row in ws.iter_rows(values_only=True):
        if any(cell is not None for cell in row):
            rows.append([str(cell) if cell is not None else "" for cell in row])
    wb.close()
    return rows


# ── Public API ────────────────────────────────────────────────────────────────

def store_upload(file_bytes: bytes, filename: str) -> dict:
    """
    Parse the file and cache it.  Returns preview data for the mapping UI.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "csv":
        raw = _parse_csv(file_bytes)
    elif ext in ("xlsx", "xls"):
        raw = _parse_excel(file_bytes)
    else:
        raise ValueError(f"Unsupported file type '.{ext}'. Please upload a CSV or Excel file.")

    columns, data_rows = _clean_rows(raw)

    upload_id = uuid.uuid4().hex[:12]
    _uploads[upload_id] = {"columns": columns, "rows": data_rows}

    return {
        "upload_id":  upload_id,
        "filename":   filename,
        "columns":    columns,
        "preview":    data_rows[:5],
        "total_rows": len(data_rows),
    }


def do_import(upload_id: str, mapping: dict, user_id=None) -> dict:
    """
    Apply field mapping and persist trades.
    mapping = { "order_date": "col_name", "ticker": "col_name", ... }
    Returns {"imported": N, "errors": [...]}
    """
    import database as db

    if upload_id not in _uploads:
        raise ValueError("Upload session not found — please upload the file again.")

    cached   = _uploads.pop(upload_id)
    columns  = cached["columns"]
    rows     = cached["rows"]
    col_idx  = {c: i for i, c in enumerate(columns)}

    def cell(row, field):
        col = mapping.get(field, "")
        if not col:
            return ""
        idx = col_idx.get(col)
        if idx is None or idx >= len(row):
            return ""
        return row[idx].strip()

    imported, errors = 0, []

    for i, row in enumerate(rows, 1):
        try:
            date_str  = cell(row, "order_date")
            ticker    = cell(row, "ticker").upper()
            units_str = cell(row, "units")
            price_str = cell(row, "price")
            amt_str   = cell(row, "amount")
            broker    = cell(row, "broker") or ""

            if not date_str or not ticker:
                errors.append(f"Row {i}: missing date or ticker — skipped.")
                continue

            order_date = _parse_date(date_str)
            price  = _parse_num(price_str)
            units  = _parse_num(units_str)
            amount = _parse_num(amt_str)

            if price <= 0:
                errors.append(f"Row {i} ({ticker}): price is zero or missing — skipped.")
                continue
            if units <= 0 and amount <= 0:
                errors.append(f"Row {i} ({ticker}): need at least units or total amount — skipped.")
                continue
            if units <= 0:
                units = round(amount / price, 4)
            if amount <= 0:
                amount = round(units * price, 2)

            db.add_trade(order_date, ticker, units, price, amount, broker, user_id)
            imported += 1

        except Exception as e:
            errors.append(f"Row {i}: {e}")

    return {"imported": imported, "errors": errors}
