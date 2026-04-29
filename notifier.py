"""
Email alert sender. Configure via environment variables:
  SMTP_HOST  (default: smtp.gmail.com)
  SMTP_PORT  (default: 587)
  SMTP_USER  — your email address / login
  SMTP_PASS  — app password or SMTP password
  SMTP_FROM  (default: SMTP_USER)
"""

import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)


def _smtp_configured() -> bool:
    return bool(SMTP_USER and SMTP_PASS)


def send_price_alert(to_email: str, ticker: str, name: str,
                     condition: str, limit_price: float, current_price: float):
    if not to_email:
        return
    if not _smtp_configured():
        logger.warning("SMTP not configured — skipping email for alert %s", ticker)
        return

    direction = "risen above" if condition == "above" else "fallen below"
    subject = f"GSE Price Alert: {ticker} has {direction} GHS {limit_price:.2f}"
    body = f"""\
Your price alert for {ticker} ({name}) has been triggered.

  Condition : price {direction} GHS {limit_price:.2f}
  Current   : GHS {current_price:.4f}

Log in to your GSE Portfolio Tracker to review your holdings.
"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SMTP_FROM
    msg["To"]      = to_email
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_FROM, [to_email], msg.as_string())
        logger.info("Alert email sent to %s for %s", to_email, ticker)
    except Exception as e:
        logger.error("Failed to send alert email: %s", e)
