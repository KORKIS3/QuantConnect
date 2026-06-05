"""Download 5-second YM bars from IB for recent months.

IB limits 5-second data to about 60 days of history.
Each request can get 1 hour of 5-sec bars (720 bars).
A full day (9:30-17:00 = 7.5 hours) needs ~8 requests.
"""

import asyncio
asyncio.set_event_loop(asyncio.new_event_loop())

import os, time, argparse
from datetime import date, timedelta
import pandas as pd
import pytz
from ib_insync import IB, Future

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "5sec")
os.makedirs(_DATA_ROOT, exist_ok=True)


def trading_days(start, end):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def resolve_front_month(ib, target_date):
    """Get the front-month YM contract for a given date."""
    base = Future(symbol="YM", exchange="CBOT", currency="USD", includeExpired=True)
    all_contracts = sorted(
        [d.contract for d in ib.reqContractDetails(base)],
        key=lambda c: c.lastTradeDateOrContractMonth,
    )
    d_str = target_date.strftime("%Y%m%d")
    for c in all_contracts:
        if c.lastTradeDateOrContractMonth >= d_str:
            return c
    return all_contracts[-1]


def download_day(ib, contract, d):
    """Download 5-sec bars for one full day (9:30-17:00 ET) in hourly chunks."""
    fname = os.path.join(_DATA_ROOT, f"CBOT_MINI_YM1_{d}_5sec.csv")
    if os.path.exists(fname):
        return True  # already downloaded

    all_bars = []

    # Request in 1-hour chunks from 9:30 to 17:00
    # IB reqHistoricalData with 5 secs bars: max durationStr = "3600 S" (1 hour)
    start_hour = 9
    start_min = 30
    hours = [
        (9, 30, 10, 30),
        (10, 30, 11, 30),
        (11, 30, 12, 30),
        (12, 30, 13, 30),
        (13, 30, 14, 30),
        (14, 30, 15, 30),
        (15, 30, 16, 30),
        (16, 30, 17, 0),
    ]

    for h_start_h, h_start_m, h_end_h, h_end_m in hours:
        end_ts = pd.Timestamp(f"{d} {h_end_h:02d}:{h_end_m:02d}:00")
        end_ts = end_ts.tz_localize(_EST).astimezone(pytz.utc)
        end_str = end_ts.strftime("%Y%m%d-%H:%M:%S")

        try:
            bars = ib.reqHistoricalData(
                contract,
                endDateTime=end_str,
                durationStr="3600 S",
                barSizeSetting="5 secs",
                whatToShow="TRADES",
                useRTH=False,
                formatDate=1,
                timeout=15,
            )
        except Exception as exc:
            print(f"    Error chunk {h_start_h}:{h_start_m:02d}-{h_end_h}:{h_end_m:02d}: {exc}")
            continue

        if bars:
            all_bars.extend(bars)
        time.sleep(10)  # IB pacing: max 6 requests/min for 5-sec data

    if not all_bars:
        print(f"  {d}: no data")
        return False

    df = pd.DataFrame(
        [
            {
                "time": b.date,
                "Open": b.open,
                "High": b.high,
                "Low": b.low,
                "Close": b.close,
                "Volume": b.volume,
            }
            for b in all_bars
        ]
    ).set_index("time")
    df.index = pd.to_datetime(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(_EST)
    else:
        df.index = df.index.tz_convert(_EST)

    # Filter to day session only
    day_start = pd.Timestamp(f"{d} 09:30", tz=_EST)
    day_end = pd.Timestamp(f"{d} 17:00", tz=_EST)
    df = df[(df.index >= day_start) & (df.index <= day_end)]

    # Remove duplicates
    df = df[~df.index.duplicated(keep="first")]
    df = df.sort_index()

    if len(df) < 100:
        print(f"  {d}: only {len(df)} bars, skipping")
        return False

    df.to_csv(fname)
    print(f"  {d} ({contract.localSymbol}): {len(df)} bars saved")
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=4002, help="IB port (4001=live, 4002=paper)")
    p.add_argument("--days", type=int, default=60, help="Number of trading days to download")
    args = p.parse_args()

    ib = IB()
    ib.connect("127.0.0.1", args.port, clientId=55, timeout=120)
    print(f"Connected to IB on port {args.port}")

    end_date = date.today() - timedelta(days=1)  # yesterday
    start_date = end_date - timedelta(days=20)  # only last ~2 weeks (safe for 5-sec on paper)

    days = [d for d in trading_days(start_date, end_date)]
    if len(days) > args.days:
        days = days[-args.days:]
    print(f"Downloading 5-sec bars for {len(days)} trading days...")
    print(f"Output: {_DATA_ROOT}\n")

    contract = resolve_front_month(ib, days[0])
    success = 0
    for i, d in enumerate(days):
        # Check if we need a new front month
        new_contract = resolve_front_month(ib, d)
        if new_contract.localSymbol != contract.localSymbol:
            contract = new_contract

        print(f"[{i+1}/{len(days)}] {d}...", end="", flush=True)
        if download_day(ib, contract, d):
            success += 1
        else:
            print()
        time.sleep(1)  # pacing between days

    ib.disconnect()
    print(f"\nDone. {success}/{len(days)} days downloaded to {_DATA_ROOT}")


if __name__ == "__main__":
    main()
