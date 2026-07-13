"""download_yesterday.py

Downloads the previous trading day's full 1-minute bar data from IB
and saves it to ~/Desktop/2YearsData/full_day/.

Run manually or schedule via Windows Task Scheduler to run each morning.

Usage:
    python download_yesterday.py           # downloads yesterday
    python download_yesterday.py 2026-04-18  # downloads a specific date
"""

import asyncio
asyncio.set_event_loop(asyncio.new_event_loop())

import os
import sys
import time
import logging
from datetime import date, timedelta

import pandas as pd
import pytz
from ib_async import IB, Future

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

_EST      = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
IB_HOST   = "127.0.0.1"
IB_PORT   = 4002   # paper — change to 4001 for live
IB_CLIENT = 98     # unique client ID so it doesn't conflict with live session


def prev_trading_day(from_date: date) -> date:
    """Return the most recent weekday before from_date."""
    d = from_date - timedelta(days=1)
    while d.weekday() >= 5:  # skip Sat/Sun
        d -= timedelta(days=1)
    return d


def download_day(date_str: str, ib: IB, contract) -> bool:
    """Download full 1-min bars for date_str. Returns True on success."""
    fname = os.path.join(DATA_ROOT, f"CBOT_MINI_YM1_{date_str}.csv")

    end_utc = (pd.Timestamp(f"{date_str} 23:59:00")
               .tz_localize(_EST)
               .astimezone(pytz.utc)
               .strftime("%Y%m%d-%H:%M:%S"))

    log.info("Fetching %s from %s ...", date_str, contract.localSymbol)
    try:
        bars = ib.reqHistoricalData(
            contract,
            endDateTime=end_utc,
            durationStr="2 D",
            barSizeSetting="1 min",
            whatToShow="TRADES",
            useRTH=False,
            formatDate=1,
        )
    except Exception as exc:
        log.error("reqHistoricalData error: %s", exc)
        return False

    if not bars:
        log.warning("No data returned for %s", date_str)
        return False

    df = pd.DataFrame([{
        "time":   b.date,
        "Open":   b.open,
        "High":   b.high,
        "Low":    b.low,
        "Close":  b.close,
        "Volume": b.volume,
    } for b in bars]).set_index("time")

    df.index = pd.to_datetime(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(_EST)
    else:
        df.index = df.index.tz_convert(_EST)

    # Keep only bars from the requested date
    df = df[df.index.strftime("%Y-%m-%d") == date_str]

    if df.empty:
        log.warning("No bars found for %s after filtering", date_str)
        return False

    os.makedirs(DATA_ROOT, exist_ok=True)
    df.to_csv(fname)
    log.info("Saved %d bars → %s", len(df), fname)
    return True


def main():
    # Determine which date to download
    if len(sys.argv) > 1:
        target = sys.argv[1]
    else:
        target = prev_trading_day(date.today()).strftime("%Y-%m-%d")

    log.info("Target date: %s", target)

    # Check if already complete (1380 bars = full day)
    fname = os.path.join(DATA_ROOT, f"CBOT_MINI_YM1_{target}.csv")
    if os.path.exists(fname):
        existing = pd.read_csv(fname)
        if len(existing) >= 1380:
            log.info("%s already complete (%d bars) — skipping", target, len(existing))
            return

    # Connect to IB
    ib = IB()
    try:
        ib.connect(IB_HOST, IB_PORT, clientId=IB_CLIENT, timeout=30)
        log.info("Connected to IB at %s:%d", IB_HOST, IB_PORT)
    except Exception as exc:
        log.error("Could not connect to IB: %s", exc)
        log.error("Make sure IB Gateway is running on port %d", IB_PORT)
        sys.exit(1)

    # Find front-month contract
    try:
        base = Future(symbol="YM", exchange="CBOT", currency="USD", includeExpired=True)
        all_contracts = sorted(
            [d.contract for d in ib.reqContractDetails(base)],
            key=lambda c: c.lastTradeDateOrContractMonth,
        )
        date_key = target.replace("-", "")
        contract = next(
            (c for c in all_contracts if c.lastTradeDateOrContractMonth >= date_key),
            all_contracts[-1],
        )
        log.info("Contract: %s  expiry=%s", contract.localSymbol,
                 contract.lastTradeDateOrContractMonth)
    except Exception as exc:
        log.error("Could not resolve contract: %s", exc)
        ib.disconnect()
        sys.exit(1)

    # Download
    success = download_day(target, ib, contract)
    ib.disconnect()
    log.info("Disconnected from IB")

    if success:
        log.info("Done — %s downloaded successfully", target)
    else:
        log.error("Failed to download %s", target)
        sys.exit(1)


if __name__ == "__main__":
    main()
