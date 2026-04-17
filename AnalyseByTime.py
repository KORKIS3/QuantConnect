"""Analyse win rate and P/L by time-of-day buckets."""

import os
import pandas as pd
import pytz
import numpy as np
from TradingAlgo import run_trading_algo, AlgoConfig

_EST       = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1130")
_CONTRACTS = 2
_MULTIPLIER = 5

config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=10)

csv_files = sorted([
    f for f in os.listdir(_DATA_ROOT)
    if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")
])

all_trades = []

for fname in csv_files:
    target_date = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
    fpath = os.path.join(_DATA_ROOT, fname)
    try:
        df = pd.read_csv(fpath, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        if len(df) < 10:
            continue
        algo_df = run_trading_algo(df, target_date, "09:30", "11:30", config=config)
    except Exception:
        continue

    signals = algo_df[algo_df["signal"].isin(["BUY","SELL"])].copy()
    if signals.empty:
        continue

    sig_list = [(ts, row["signal"],
                 float(row["buy_price"] if row["signal"]=="BUY" else row["sell_price"]))
                for ts, row in signals.iterrows()]

    position = "flat"
    entry_price = None
    entry_time  = None

    for ts, sig, price in sig_list:
        if sig == "BUY":
            if position == "short" and entry_price is not None:
                pl = entry_price - price
                all_trades.append({"entry_time": entry_time, "exit_time": ts,
                                   "direction": "SHORT", "pl": pl,
                                   "entry_hhmm": entry_time.strftime("%H:%M")})
            position, entry_price, entry_time = "long", price, ts
        elif sig == "SELL":
            if position == "long" and entry_price is not None:
                pl = price - entry_price
                all_trades.append({"entry_time": entry_time, "exit_time": ts,
                                   "direction": "LONG", "pl": pl,
                                   "entry_hhmm": entry_time.strftime("%H:%M")})
            position, entry_price, entry_time = "short", price, ts

    # Open position at session end
    if position != "flat" and entry_price is not None:
        last_close = float(algo_df["Close"].iloc[-1])
        pl = (last_close - entry_price) if position == "long" else (entry_price - last_close)
        all_trades.append({"entry_time": entry_time, "exit_time": algo_df.index[-1],
                           "direction": position.upper(), "pl": pl,
                           "entry_hhmm": entry_time.strftime("%H:%M")})

trades_df = pd.DataFrame(all_trades)
trades_df["entry_minute"] = trades_df["entry_time"].apply(lambda t: t.hour * 60 + t.minute)

# Bucket by 15-minute windows
buckets = [
    ("09:42-09:59", 9*60+42, 9*60+59),
    ("10:00-10:14", 10*60+0, 10*60+14),
    ("10:15-10:29", 10*60+15, 10*60+29),
    ("10:30-10:44", 10*60+30, 10*60+44),
    ("10:45-10:59", 10*60+45, 10*60+59),
    ("11:00-11:14", 11*60+0, 11*60+14),
    ("11:15-11:30", 11*60+15, 11*60+30),
]

print(f"Total trades: {len(trades_df)}")
print(f"\n{'Time Window':<16} {'Trades':>7} {'Winners':>8} {'Losers':>7} {'Win%':>6} {'Avg P/L':>8} {'Total':>8}")
print("-" * 68)

for label, start_min, end_min in buckets:
    bucket = trades_df[(trades_df["entry_minute"] >= start_min) &
                       (trades_df["entry_minute"] <= end_min)]
    if bucket.empty:
        print(f"{label:<16} {'—':>7}")
        continue
    winners = sum(1 for p in bucket["pl"] if p > 0)
    losers  = sum(1 for p in bucket["pl"] if p <= 0)
    win_pct = winners / len(bucket) * 100
    avg_pl  = bucket["pl"].mean()
    total   = bucket["pl"].sum()
    print(f"{label:<16} {len(bucket):>7} {winners:>8} {losers:>7} {win_pct:>5.1f}% {avg_pl:>+7.1f} {total:>+8.0f}")

print(f"\nCumulative P/L by extending session end:")
running = 0
for label, start_min, end_min in buckets:
    bucket = trades_df[(trades_df["entry_minute"] >= start_min) &
                       (trades_df["entry_minute"] <= end_min)]
    running += bucket["pl"].sum()
    print(f"  Through {label}: {running:+.0f} pts  ${running*_CONTRACTS*_MULTIPLIER:+,.0f}")
