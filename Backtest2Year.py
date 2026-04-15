"""Backtest2Year.py

Downloads 2 years of YM 9:30-10:30 ET data from IB, runs the trading algo
with multiple reversal filter variants, and prints a comparison table.

Usage:
    python Backtest2Year.py --port 4001
    python Backtest2Year.py --skip-download   # use existing CSVs
"""

import argparse
import os
import time
import pandas as pd
import pytz
from datetime import date, timedelta
from ib_insync import IB, Future

from TradingAlgo import run_trading_algo, AlgoConfig

_EST        = pytz.timezone("US/Eastern")
_DATA_ROOT  = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1000")
_CONTRACTS  = 100
_MULTIPLIER = 5


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def trading_days(start: date, end: date):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


def download_all(port: int) -> None:
    ib = IB()
    ib.connect("127.0.0.1", port, clientId=20)
    print(f"Connected to IB port {port}")

    # Get all YM contracts including expired ones.
    base = Future(symbol="YM", exchange="CBOT", currency="USD",
                  includeExpired=True)
    all_details = ib.reqContractDetails(base)
    # Sort by expiry ascending.
    all_contracts = sorted(
        [d.contract for d in all_details],
        key=lambda c: c.lastTradeDateOrContractMonth
    )
    print(f"Found {len(all_contracts)} YM contracts (including expired)")

    def front_month_for(d: date) -> object:
        """Return the contract whose expiry is on or after date d."""
        d_str = d.strftime("%Y%m%d")
        for c in all_contracts:
            if c.lastTradeDateOrContractMonth >= d_str:
                return c
        return all_contracts[-1]

    os.makedirs(_DATA_ROOT, exist_ok=True)
    end_date   = date.today()
    start_date = end_date - timedelta(days=365 * 2 + 30)
    days = list(trading_days(start_date, end_date))
    print(f"Downloading {len(days)} days ...")
    for idx, d in enumerate(days):
        fname = os.path.join(_DATA_ROOT, f"CBOT_MINI_YM1_{d}.csv")
        if os.path.exists(fname):
            continue
        contract = front_month_for(d)
        end_ts  = pd.Timestamp(f"{d} 10:35:00").tz_localize(_EST).astimezone(pytz.utc)
        end_utc = end_ts.strftime("%Y%m%d-%H:%M:%S")

        try:
            bars = ib.reqHistoricalData(contract, endDateTime=end_utc,
                durationStr="4200 S", barSizeSetting="1 min",
                whatToShow="TRADES", useRTH=False, formatDate=1)
        except Exception as exc:
            print(f"  {d}: ERROR {exc}"); continue
        if not bars:
            print(f"  {d}: no data"); continue
        df = pd.DataFrame([{"time": b.date, "Open": b.open, "High": b.high,
                             "Low": b.low, "Close": b.close, "Volume": b.volume}
                            for b in bars]).set_index("time")
        df.index = pd.to_datetime(df.index)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert(_EST)
        else:
            df.index = df.index.tz_convert(_EST)
        # Filter strictly to 09:30-10:30 ET.
        t_start = pd.Timestamp(f"{d} 09:30:00", tz=_EST)
        t_end   = pd.Timestamp(f"{d} 10:30:00", tz=_EST)
        df = df[(df.index >= t_start) & (df.index <= t_end)]
        if len(df) < 10:
            continue
        df.to_csv(fname)
        print(f"  [{idx+1}/{len(days)}] {d}: {len(df)} bars")
        time.sleep(0.5)
    ib.disconnect()
    print("Download complete.")


# ---------------------------------------------------------------------------
# Core P/L calculator from a filtered signal list
# ---------------------------------------------------------------------------

def calc_pl(filtered: list, last_close: float) -> list:
    """Given [(ts, sig, price), ...] return list of per-trade P/L points."""
    trade_pls = []
    position  = "flat"
    entry_price = None
    for ts, sig, price in filtered:
        if sig == "BUY":
            if position == "short" and entry_price is not None:
                trade_pls.append(entry_price - price)
            position    = "long"
            entry_price = price
        elif sig == "SELL":
            if position == "long" and entry_price is not None:
                trade_pls.append(price - entry_price)
            position    = "short"
            entry_price = price
    if position != "flat" and entry_price is not None:
        if position == "long":
            trade_pls.append(last_close - entry_price)
        else:
            trade_pls.append(entry_price - last_close)
    return trade_pls


# ---------------------------------------------------------------------------
# Variant runner
# ---------------------------------------------------------------------------

def run_variant(algo_df: pd.DataFrame, variant: str,
                min_profit: float = 0, min_minutes: int = 0,
                min_cross_pts: float = 0,
                steep_angle_threshold: float = 65.0) -> dict:

    signals = algo_df[algo_df["signal"].isin(["BUY", "SELL"])].copy()
    last_close = float(algo_df["Close"].iloc[-1])

    if signals.empty:
        return {"variant": variant, "trades": 0, "pl_pts": 0.0,
                "winners": 0, "losers": 0}

    # Option 2: min_cross_pts — require close to be X pts beyond the ray.
    # We approximate this by checking the distance between close and the
    # triggering ray at signal time.
    def cross_distance(row):
        sig = row["signal"]
        price = float(row["buy_price"] if sig == "BUY" else row["sell_price"])
        if sig == "BUY":
            ray = min(
                float(row.get("orange_ray", float("inf"))),
                float(row.get("purple_ray", float("inf"))),
                float(row.get("magenta_ray", float("inf"))),
            )
            return price - ray if ray != float("inf") else 999
        else:
            ray = max(
                float(row.get("yellow_ray", float("-inf"))),
                float(row.get("blue_ray",   float("-inf"))),
                float(row.get("lime_ray",   float("-inf"))),
            )
            return ray - price if ray != float("-inf") else 999

    filtered = []
    for ts, row in signals.iterrows():
        sig   = row["signal"]
        price = float(row["buy_price"] if sig == "BUY" else row["sell_price"])

        # Option 2 filter — apply to ALL signals, not just reversals.
        if min_cross_pts > 0:
            dist = cross_distance(row)
            if dist < min_cross_pts:
                continue

        if not filtered:
            filtered.append((ts, sig, price))
            continue

        last_ts, last_sig, last_price = filtered[-1]
        is_reversal = (last_sig != sig)

        if is_reversal:
            mins_held = (ts - last_ts).total_seconds() / 60
            if last_sig == "BUY":
                profit_so_far = price - last_price
            else:
                profit_so_far = last_price - price

            allow = True
            profit_ok = (min_profit == 0 or profit_so_far >= min_profit)
            time_ok   = (min_minutes == 0 or mins_held >= min_minutes)

            if min_profit > 0 and min_minutes > 0:
                # combined: need EITHER profit OR time
                allow = profit_ok or time_ok
            elif min_profit > 0:
                allow = profit_ok
            elif min_minutes > 0:
                allow = time_ok

            if allow:
                filtered.append((ts, sig, price))
        else:
            filtered.append((ts, sig, price))

    trade_pls = calc_pl(filtered, last_close)
    if not trade_pls:
        return {"variant": variant, "trades": 0, "pl_pts": 0.0,
                "winners": 0, "losers": 0}

    return {
        "variant":  variant,
        "trades":   len(trade_pls),
        "pl_pts":   round(sum(trade_pls), 1),
        "winners":  sum(1 for p in trade_pls if p > 0),
        "losers":   sum(1 for p in trade_pls if p <= 0),
    }


# ---------------------------------------------------------------------------
# Main backtest
# ---------------------------------------------------------------------------

def run_backtest() -> None:
    csv_files = sorted([
        f for f in os.listdir(_DATA_ROOT)
        if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")
    ])
    print(f"\nRunning backtest on {len(csv_files)} days ...\n")

    variants = [
        ("no_threshold",   dict(steep_angle_threshold=999)),
        ("threshold_45",   dict(steep_angle_threshold=45)),
        ("threshold_55",   dict(steep_angle_threshold=55)),
        ("threshold_65",   dict(steep_angle_threshold=65)),
        ("threshold_70",   dict(steep_angle_threshold=70)),
        ("threshold_75",   dict(steep_angle_threshold=75)),
        ("threshold_80",   dict(steep_angle_threshold=80)),
        ("threshold_90",   dict(steep_angle_threshold=90)),
    ]

    totals = {v[0]: {"trades":0,"pl_pts":0.0,"winners":0,"losers":0} for v in variants}
    days_run = 0

    for fname in csv_files:
        target_date = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
        fpath = os.path.join(_DATA_ROOT, fname)
        try:
            df = pd.read_csv(fpath, index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
            if len(df) < 10:
                continue
        except Exception:
            continue

        days_run += 1
        if days_run % 50 == 0:
            print(f"  ... {days_run}/{len(csv_files)} days processed")
        for vname, vkwargs in variants:
            try:
                algo_df = run_trading_algo(df, target_date, "09:30", "10:30",
                    config=AlgoConfig(
                        warmup_minutes=7,
                        steep_angle_threshold=vkwargs.get("steep_angle_threshold", 65.0),
                        proximity_points=15.0,
                        min_reversal_minutes=0,  # filter applied by run_variant below
                    ))
            except Exception:
                continue
            result = run_variant(algo_df, vname, min_minutes=10)
            if result:
                totals[vname]["trades"]  += result["trades"]
                totals[vname]["pl_pts"]  += result["pl_pts"]
                totals[vname]["winners"] += result["winners"]
                totals[vname]["losers"]  += result["losers"]

    print(f"Days analysed: {days_run}")
    print(f"Contracts:     {_CONTRACTS} x ${_MULTIPLIER}/pt\n")
    print(f"{'Variant':<18} {'Trades':>7} {'Winners':>8} {'Losers':>7} {'Win%':>6} {'P/L pts':>10} {'P/L USD':>14}")
    print("-" * 80)
    for vname, _ in variants:
        t = totals[vname]
        trades   = t["trades"]
        win_rate = t["winners"] / trades * 100 if trades else 0
        pl_usd   = t["pl_pts"] * _CONTRACTS * _MULTIPLIER
        print(f"{vname:<18} {trades:>7} {t['winners']:>8} {t['losers']:>7} "
              f"{win_rate:>5.1f}% {t['pl_pts']:>10.0f} ${pl_usd:>13,.0f}")
    print()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--port",          type=int, default=4001)
    p.add_argument("--skip-download", action="store_true", dest="skip_download")
    args = p.parse_args()
    if not args.skip_download:
        download_all(args.port)
    run_backtest()
