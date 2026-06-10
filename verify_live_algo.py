"""VERIFICATION: Run the exact live algo config through the backtest.
No modifications, no post-hoc filters, no external P/L replay.
Just the engine's session_pl with the exact config from InteractiveBrokers.py.
cushion_points defaults to 0.0 (not set in live config = instant fills in engine).
"""
import os
import pandas as pd
import numpy as np
import pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

# EXACT live config from InteractiveBrokers.py line 274
live_config = AlgoConfig(
    warmup_minutes=7,
    steep_angle_threshold=90.0,
    proximity_points=4.0,
    min_reversal_minutes=0,
    min_entry_angle=0.0,
    partial_tp_pts=50.0,
    spike_profit_pts=100.0,
    spike_profit_bars=9,
    wm_shield_distance=0.0,
    swing_anchor_threshold=10.0,
    num_contracts=2,
)

csv_files = sorted([f for f in os.listdir(_DATA_ROOT)
                    if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])

daily_pls = []
skipped = 0

for i, fname in enumerate(csv_files):
    target_date = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
    fpath = os.path.join(_DATA_ROOT, fname)

    try:
        df = pd.read_csv(fpath, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        if len(df) < 15:
            skipped += 1
            continue
        if (df[["Open", "High", "Low", "Close"]] <= 0).any().any():
            skipped += 1
            continue
        if df["High"].max() == df["Low"].min():
            skipped += 1
            continue
        if df["Volume"].sum() < 100:
            skipped += 1
            continue

        day_start = pd.Timestamp(f"{target_date} 09:30", tz=_EST)
        day_end = pd.Timestamp(f"{target_date} 16:59", tz=_EST)
        day_data = df[(df.index >= day_start) & (df.index <= day_end)]
        if len(day_data) < 15:
            skipped += 1
            continue

        algo_df = run_trading_algo_fast(day_data, target_date, "09:30", "17:00", config=live_config)

        end_ts = pd.Timestamp(f"{target_date} 17:00", tz=_EST)
        sliced = algo_df[(algo_df.index >= day_start) & (algo_df.index <= end_ts)]
        if len(sliced) < 2:
            skipped += 1
            continue

        pl = float(sliced["session_pl"].iloc[-1])
        daily_pls.append(pl)

    except Exception as exc:
        skipped += 1
        continue

    if (i + 1) % 100 == 0:
        print(f"  [{i+1}/{len(csv_files)}] {len(daily_pls)} days processed...", flush=True)

arr = np.array(daily_pls)

print(f"\n{'='*60}", flush=True)
print(f"LIVE ALGO VERIFICATION", flush=True)
print(f"Config: warmup=7, steep=90, proximity=4, wm_shield=0,", flush=True)
print(f"        swing_anchor=10, spike_profit=100/9, partial_tp=50", flush=True)
print(f"        cushion=0 (instant fills), min_reversal=0", flush=True)
print(f"Engine: current TradingAlgoFast.py (session_pl directly)", flush=True)
print(f"{'='*60}", flush=True)
print(f"Total CSV files: {len(csv_files)}", flush=True)
print(f"Skipped: {skipped}", flush=True)
print(f"Days with results: {len(arr)}", flush=True)
print(f"Days with P/L != 0: {(arr != 0).sum()}", flush=True)
print(f"Days with P/L == 0: {(arr == 0).sum()}", flush=True)
print(f"", flush=True)
print(f"Total pts: {arr.sum():+.0f}", flush=True)
print(f"Avg pts/day (all): {arr.mean():+.1f}", flush=True)
nonzero = arr[arr != 0]
if len(nonzero) > 0:
    print(f"Avg pts/day (traded days only): {nonzero.mean():+.1f}", flush=True)
print(f"Win days: {(arr > 0).sum()} ({(arr > 0).sum()/len(arr)*100:.1f}%)", flush=True)
print(f"Lose days: {(arr < 0).sum()} ({(arr < 0).sum()/len(arr)*100:.1f}%)", flush=True)
print(f"Flat days: {(arr == 0).sum()}", flush=True)
print(f"Best day: {arr.max():+.0f}", flush=True)
print(f"Worst day: {arr.min():+.0f}", flush=True)
print(f"Std dev: {arr.std():.1f}", flush=True)
cum = np.cumsum(arr)
dd = (cum - np.maximum.accumulate(cum)).min()
print(f"Max drawdown: {dd:+.0f}", flush=True)
