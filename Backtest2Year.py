"""Backtest2Year.py

Downloads 2 years of YM 9:30-10:30 ET data from IB and backtests
the trading algo with configurable variants.

Usage:
    python Backtest2Year.py --port 4001              # download + backtest
    python Backtest2Year.py --skip-download          # backtest only
    python Backtest2Year.py --skip-download --max-days 50  # quick sample
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
_CONTRACTS  = 2
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

    base = Future(symbol="YM", exchange="CBOT", currency="USD", includeExpired=True)
    all_contracts = sorted(
        [d.contract for d in ib.reqContractDetails(base)],
        key=lambda c: c.lastTradeDateOrContractMonth
    )
    print(f"Found {len(all_contracts)} YM contracts")

    def front_month_for(d: date):
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
        end_utc  = pd.Timestamp(f"{d} 10:35:00").tz_localize(_EST).astimezone(pytz.utc).strftime("%Y%m%d-%H:%M:%S")
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
        df = df[(df.index >= pd.Timestamp(f"{d} 09:30", tz=_EST)) &
                (df.index <= pd.Timestamp(f"{d} 10:30", tz=_EST))]
        if len(df) < 10:
            continue
        df.to_csv(fname)
        print(f"  [{idx+1}/{len(days)}] {d}: {len(df)} bars")
        time.sleep(0.5)

    ib.disconnect()
    print("Download complete.")


# ---------------------------------------------------------------------------
# P/L calculator
# ---------------------------------------------------------------------------

def calc_pl(signals_df: pd.DataFrame, last_close: float,
            min_minutes: int = 0, flat_window: tuple = None) -> list:
    """Calculate per-trade P/L applying the time-based reversal filter.
    
    flat_window: optional (start_minute, end_minute) tuple e.g. (58, 62)
    meaning go flat at :58 and resume at :02. Minutes are relative to the hour.
    """
    rows = signals_df[signals_df["signal"].isin(["BUY","SELL"])].copy()
    if rows.empty:
        return []

    filtered = []
    for ts, row in rows.iterrows():
        sig   = row["signal"]
        price = float(row["buy_price"] if sig == "BUY" else row["sell_price"])

        # Skip signals during the flat window (9:58 - 10:02)
        if flat_window is not None:
            bar_hhmm = ts.hour * 60 + ts.minute
            flat_start = 9 * 60 + flat_window[0]  # e.g. 9:58
            flat_end   = 10 * 60 + flat_window[1]  # e.g. 10:02
            if flat_start <= bar_hhmm <= flat_end:
                continue

        if not filtered:
            filtered.append((ts, sig, price))
            continue
        last_ts, last_sig, last_price = filtered[-1]
        if last_sig != sig:  # reversal
            mins_held = (ts - last_ts).total_seconds() / 60
            if min_minutes == 0 or mins_held >= min_minutes:
                filtered.append((ts, sig, price))
        else:
            filtered.append((ts, sig, price))

    # If flat_window active, force close any open position at flat_start
    # and reopen after flat_end if a signal fires.
    # For simplicity, we handle this by just skipping signals in the window above.

    trade_pls = []
    position = "flat"
    entry_price = None
    for ts, sig, price in filtered:
        if sig == "BUY":
            if position == "short" and entry_price is not None:
                trade_pls.append(entry_price - price)
            position, entry_price = "long", price
        elif sig == "SELL":
            if position == "long" and entry_price is not None:
                trade_pls.append(price - entry_price)
            position, entry_price = "short", price
    if position != "flat" and entry_price is not None:
        trade_pls.append((last_close - entry_price) if position == "long"
                         else (entry_price - last_close))
    return trade_pls


# ---------------------------------------------------------------------------
# Main backtest
# ---------------------------------------------------------------------------

def run_backtest(max_days: int = 0) -> None:
    csv_files = sorted([
        f for f in os.listdir(_DATA_ROOT)
        if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")
    ])
    if max_days > 0:
        csv_files = csv_files[-max_days:]
    print(f"\nRunning backtest on {len(csv_files)} days ...\n")

    # Define variants: (label, warmup_minutes, min_reversal_minutes, shallow_warmup_minutes)
    # shallow_warmup_minutes: earlier cutoff for orange/yellow crosses only (0 = same as warmup)
    # Define variants: (label, warmup_minutes, min_reversal_minutes, shallow_warmup, max_loss)
    # max_loss=0 means trailing stop is active (built into algo now)
    # To test without trailing stop, we'd need a separate config flag — for now
    # just run the current code which has trailing stop enabled.
    variants = [
        ("with_trailing_stop",   12, 10, 0, 0),
    ]

    totals = {v[0]: {"trades":0,"pl_pts":0.0,"winners":0,"losers":0,"daily_pls":[]} for v in variants}
    days_run = 0

    for fname in csv_files:
        target_date = fname.replace("CBOT_MINI_YM1_","").replace(".csv","")
        fpath = os.path.join(_DATA_ROOT, fname)
        try:
            df = pd.read_csv(fpath, index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
            if len(df) < 10:
                continue
        except Exception:
            continue

        days_run += 1
        if days_run % 100 == 0:
            print(f"  ... {days_run}/{len(csv_files)} days processed")

        # Skip April 2025 — extreme tariff volatility, not tradeable
        if target_date.startswith("2025-04"):
            continue

        for vname, warmup, rev_min, shallow_warmup, max_loss in variants:
            effective_warmup = shallow_warmup if shallow_warmup > 0 else warmup
            try:
                algo_df = run_trading_algo(df, target_date, "09:30", "10:30",
                    config=AlgoConfig(
                        warmup_minutes=effective_warmup,
                        steep_angle_threshold=70.0,
                        proximity_points=15.0,
                        min_reversal_minutes=0,
                        max_loss_per_trade=max_loss,
                    ))
            except Exception:
                continue

            trade_pls = calc_pl(algo_df, float(algo_df["Close"].iloc[-1]), rev_min)
            if not trade_pls:
                continue
            day_pl = sum(trade_pls)
            totals[vname]["trades"]  += len(trade_pls)
            totals[vname]["pl_pts"]  += day_pl
            totals[vname]["winners"] += sum(1 for p in trade_pls if p > 0)
            totals[vname]["losers"]  += sum(1 for p in trade_pls if p <= 0)
            totals[vname]["daily_pls"].append(day_pl)

    print(f"Days analysed: {days_run}")
    print(f"Contracts:     {_CONTRACTS} x ${_MULTIPLIER}/pt\n")
    print(f"{'Variant':<22} {'Trades':>7} {'Winners':>8} {'Losers':>7} {'Win%':>6} {'Total Pts':>10} {'P/L USD':>12}")
    print("-" * 80)
    for vname, _, _, _, _ in variants:
        t = totals[vname]
        trades   = t["trades"]
        win_rate = t["winners"] / trades * 100 if trades else 0
        pl_usd   = t["pl_pts"] * _CONTRACTS * _MULTIPLIER
        print(f"{vname:<22} {trades:>7} {t['winners']:>8} {t['losers']:>7} "
              f"{win_rate:>5.1f}% {t['pl_pts']:>10.0f} ${pl_usd:>11,.0f}")
    print()

    # Daily P/L summary
    import numpy as np
    for vname, _, _, _, _ in variants:
        daily = totals[vname]["daily_pls"]
        if not daily:
            continue
        daily = sorted(daily)
        win_days  = [d for d in daily if d > 0]
        lose_days = [d for d in daily if d <= 0]
        print(f"\n--- Daily P/L Summary ({vname}) ---")
        print(f"  Trading days:    {len(daily)}")
        print(f"  Winning days:    {len(win_days)} ({len(win_days)/len(daily)*100:.0f}%)")
        print(f"  Losing days:     {len(lose_days)} ({len(lose_days)/len(daily)*100:.0f}%)")
        print(f"  Avg daily P/L:   {np.mean(daily):+.1f} pts  ${np.mean(daily)*_CONTRACTS*_MULTIPLIER:+,.0f}")
        print(f"  Avg winning day: {np.mean(win_days):+.1f} pts" if win_days else "")
        print(f"  Avg losing day:  {np.mean(lose_days):+.1f} pts" if lose_days else "")
        print(f"  Best day:        {max(daily):+.0f} pts")
        print(f"  Worst day:       {min(daily):+.0f} pts")
        print(f"  Top 5 worst days: {daily[:5]}")
        print(f"  Top 5 best days:  {daily[-5:]}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--port",          type=int, default=4001)
    p.add_argument("--skip-download", action="store_true", dest="skip_download")
    p.add_argument("--max-days",      type=int, default=0, dest="max_days",
                   help="Limit to most recent N days (0 = all)")
    args = p.parse_args()
    if not args.skip_download:
        download_all(args.port)
    run_backtest(max_days=args.max_days)
