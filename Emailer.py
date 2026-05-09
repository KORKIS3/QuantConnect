"""Emailer.py

Sends a session summary email with the chart image attached and final P/L in the body.

Configuration is read from environment variables so credentials are never hardcoded:

    IB_EMAIL_FROM     sender address        e.g. you@gmail.com
    IB_EMAIL_TO       recipient address     e.g. you@gmail.com
    IB_EMAIL_PASS     app password          (Gmail: 16-char app password)
    IB_EMAIL_HOST     SMTP host             default: smtp.gmail.com
    IB_EMAIL_PORT     SMTP port             default: 587

Gmail setup:
    1. Enable 2-Step Verification on your Google account.
    2. Go to myaccount.google.com → Security → App passwords.
    3. Create an app password and set IB_EMAIL_PASS to that value.
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional
import logging

log = logging.getLogger(__name__)


def send_connection_failure_alert(error: str) -> None:
    """Send an email alert when Fred fails to connect to IB Gateway at startup."""
    sender    = os.environ.get("IB_EMAIL_FROM", "orkiskevin2@gmail.com")
    recipient = os.environ.get("IB_EMAIL_TO",   "orkiskevin2@gmail.com,harvell1972@gmail.com")
    password  = os.environ.get("IB_EMAIL_PASS")
    host      = os.environ.get("IB_EMAIL_HOST", "smtp.gmail.com")
    port      = int(os.environ.get("IB_EMAIL_PORT", "587"))

    if not password:
        return

    from datetime import datetime
    import pytz
    now = datetime.now(pytz.timezone("US/Eastern")).strftime("%H:%M:%S")

    subject = f"🚨 Fred FAILED TO START — {now} ET"
    body = (
        f"Fred Connection Failure\n"
        f"{'─' * 35}\n"
        f"Time:     {now} ET\n"
        f"Error:    {error}\n"
        f"Action:   Fred did NOT start trading\n"
        f"Fix:      Check IB Gateway is running\n"
        f"          and restart Fred manually\n"
        f"{'─' * 35}\n"
    )

    msg = MIMEMultipart()
    msg["From"]    = sender
    msg["To"]      = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(host, port) as server:
            server.ehlo(); server.starttls()
            server.login(sender, password)
            recipients = [r.strip() for r in recipient.split(",")]
            server.sendmail(sender, recipients, msg.as_string())
        log.info("[Email] Connection failure alert sent")
    except Exception as exc:
        log.error("[Email] Connection failure alert failed: %s", exc)


def send_disconnect_alert(attempt: int, max_retries: int, error: str) -> None:
    """Send an email alert when Fred loses connection to IB Gateway."""
    sender    = os.environ.get("IB_EMAIL_FROM", "orkiskevin2@gmail.com")
    recipient = os.environ.get("IB_EMAIL_TO",   "orkiskevin2@gmail.com,harvell1972@gmail.com")
    password  = os.environ.get("IB_EMAIL_PASS")
    host      = os.environ.get("IB_EMAIL_HOST", "smtp.gmail.com")
    port      = int(os.environ.get("IB_EMAIL_PORT", "587"))

    if not password:
        return

    from datetime import datetime
    import pytz
    now = datetime.now(pytz.timezone("US/Eastern")).strftime("%H:%M:%S")

    subject = f"⚠️ Fred DISCONNECTED — attempt {attempt}/{max_retries} — {now} ET"
    body = (
        f"Fred Lost Connection\n"
        f"{'─' * 35}\n"
        f"Time:     {now} ET\n"
        f"Attempt:  {attempt} of {max_retries}\n"
        f"Error:    {error}\n"
        f"Action:   Reconnecting in 30 seconds...\n"
        f"{'─' * 35}\n"
    )

    msg = MIMEMultipart()
    msg["From"]    = sender
    msg["To"]      = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(host, port) as server:
            server.ehlo(); server.starttls()
            server.login(sender, password)
            recipients = [r.strip() for r in recipient.split(",")]
            server.sendmail(sender, recipients, msg.as_string())
        log.info("[Email] Disconnect alert sent")
    except Exception as exc:
        log.error("[Email] Disconnect alert failed: %s", exc)


def send_trade_alert(
    action: str,
    price: float,
    qty: int,
    session_pl: float,
    target_date: str,
    position: str,
    order_type: str = "ENTRY",
) -> None:
    """Send an email alert for every BUY/SELL/LIQUIDATE order."""
    sender    = os.environ.get("IB_EMAIL_FROM", "orkiskevin2@gmail.com")
    recipient = os.environ.get("IB_EMAIL_TO",   "orkiskevin2@gmail.com,harvell1972@gmail.com")
    password  = os.environ.get("IB_EMAIL_PASS")
    host      = os.environ.get("IB_EMAIL_HOST", "smtp.gmail.com")
    port      = int(os.environ.get("IB_EMAIL_PORT", "587"))

    if not password:
        return

    from datetime import datetime
    import pytz
    now = datetime.now(pytz.timezone("US/Eastern")).strftime("%H:%M:%S")

    pl_sign  = "+" if session_pl >= 0 else ""
    pl_emoji = "🟢" if session_pl > 0 else ("🔴" if session_pl < 0 else "⚪")
    act_emoji = "📈" if action == "BUY" else "📉"

    subject = f"Fred {act_emoji} {action} MYM @ {price:.0f}  |  {pl_emoji} P/L: {pl_sign}{session_pl:.0f} pts"

    body = (
        f"Fred Trade Alert\n"
        f"{'─' * 35}\n"
        f"Time:       {now} ET\n"
        f"Date:       {target_date}\n"
        f"Action:     {action} ({order_type})\n"
        f"Price:      {price:.0f}\n"
        f"Qty:        {qty} contracts\n"
        f"Position:   {position}\n"
        f"Session P/L: {pl_sign}{session_pl:.0f} pts  (${session_pl*0.5:.0f})\n"
        f"{'─' * 35}\n"
    )

    msg = MIMEMultipart()
    msg["From"]    = sender
    msg["To"]      = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(host, port) as server:
            server.ehlo(); server.starttls()
            server.login(sender, password)
            recipients = [r.strip() for r in recipient.split(",")]
            server.sendmail(sender, recipients, msg.as_string())
        log.info("[Email] Trade alert sent: %s @ %s", action, price)
    except Exception as exc:
        log.error("[Email] Trade alert failed: %s", exc)


def send_session_summary(
    target_date: str,
    start_time: str,
    end_time: str,
    final_pl: float,
    image_path: Optional[str] = None,
    position: str = "flat",
    csv_path: Optional[str] = None,
) -> None:
    """Send a session summary email.

    Parameters
    ----------
    target_date:  e.g. '2026-04-06'
    start_time:   e.g. '10:25'
    end_time:     e.g. '11:25'
    final_pl:     cumulative P/L in points at session end
    image_path:   path to the saved chart JPEG (attached if provided and exists)
    position:     final position ('flat', 'long', 'short')
    """
    sender    = os.environ.get("IB_EMAIL_FROM", "orkiskevin2@gmail.com")
    recipient = os.environ.get("IB_EMAIL_TO",   "orkiskevin2@gmail.com,harvell1972@gmail.com")
    password  = os.environ.get("IB_EMAIL_PASS")
    host     = os.environ.get("IB_EMAIL_HOST", "smtp.gmail.com")
    port     = int(os.environ.get("IB_EMAIL_PORT", "587"))

    if not sender or not recipient or not password:
        log.warning(
            "[Email] Skipped — set IB_EMAIL_FROM, IB_EMAIL_TO, IB_EMAIL_PASS env vars to enable."
        )
        return

    pl_sign  = "+" if final_pl >= 0 else ""
    pl_emoji = "🟢" if final_pl > 0 else ("🔴" if final_pl < 0 else "⚪")
    subject  = f"YM Session {target_date} {pl_emoji} P/L: {pl_sign}{final_pl:.0f} pts"

    body = (
        f"YM Futures Session Summary\n"
        f"{'─' * 35}\n"
        f"Date:       {target_date}\n"
        f"Window:     {start_time} – {end_time} ET\n"
        f"Final P/L:  {pl_sign}{final_pl:.0f} points\n"
        f"Position:   {position}\n"
        f"{'─' * 35}\n"
    )
    if image_path and os.path.exists(image_path):
        body += f"Chart attached: {os.path.basename(image_path)}\n"
    else:
        body += "No chart image available.\n"
    if csv_path and os.path.exists(csv_path):
        body += f"CSV attached: {os.path.basename(csv_path)}\n"

    msg = MIMEMultipart()
    msg["From"]    = sender
    msg["To"]      = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    # Attach chart image if available.
    if image_path and os.path.exists(image_path):
        try:
            with open(image_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(image_path)}")
            msg.attach(part)
        except Exception as exc:
            log.warning("[Email] Could not attach image: %s", exc)

    # Attach CSV if available.
    if csv_path and os.path.exists(csv_path):
        try:
            with open(csv_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(csv_path)}")
            msg.attach(part)
        except Exception as exc:
            log.warning("[Email] Could not attach CSV: %s", exc)

    try:
        with smtplib.SMTP(host, port) as server:
            server.ehlo()
            server.starttls()
            server.login(sender, password)
            recipients = [r.strip() for r in recipient.split(",")]
            msg["To"] = recipient
            server.sendmail(sender, recipients, msg.as_string())
        log.info("[Email] Session summary sent to %s", recipient)
    except Exception as exc:
        log.error("[Email] Failed to send: %s", exc)
