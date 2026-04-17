"""Notifier.py

Sends SMS alerts when a BUY or SELL signal fires.

Uses Twilio. Set these environment variables:

    TWILIO_ACCOUNT_SID   your Twilio account SID
    TWILIO_AUTH_TOKEN    your Twilio auth token
    TWILIO_FROM          your Twilio phone number  e.g. +12015551234
    TWILIO_TO            your personal number       e.g. +12015559999

Twilio free trial: https://www.twilio.com/try-twilio
"""

import os
import logging

log = logging.getLogger(__name__)


def send_signal_alert(signal: str, price: float, target_date: str, bar_time) -> None:
    """Send an SMS when a BUY or SELL signal fires.

    Parameters
    ----------
    signal:      'BUY' or 'SELL'
    price:       execution price
    target_date: e.g. '2026-04-07'
    bar_time:    datetime of the bar
    """
    sid   = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_ = os.environ.get("TWILIO_FROM")
    to    = os.environ.get("TWILIO_TO")

    if not all([sid, token, from_, to]):
        log.debug("[SMS] Skipped — set TWILIO_* env vars to enable alerts.")
        return

    emoji = "🟢" if signal == "BUY" else "🔴"
    time_str = bar_time.strftime("%H:%M") if hasattr(bar_time, "strftime") else str(bar_time)
    body = f"{emoji} YM {signal} @ {int(price)}  {target_date} {time_str} ET"

    try:
        from twilio.rest import Client
        Client(sid, token).messages.create(body=body, from_=from_, to=to)
        log.info("[SMS] Sent: %s", body)
    except ImportError:
        log.warning("[SMS] twilio package not installed. Run: pip install twilio")
    except Exception as exc:
        log.error("[SMS] Failed: %s", exc)
