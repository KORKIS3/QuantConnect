"""Engine 89 full backtest with 60pt SL baked in + hourly breakdown.
Uses engine's session_pl at each end-time cutoff.
Then applies 60pt SL via the MAE method (cap per-trade losses at 60pts).

Engine 89 config: warmup=12, steep=70, proximity=15, wm_shield=12,
                  swing_anchor=10, partial_tp=50, cushion=0
"""
import os
import pandas as pd
import numpy as np
import pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

config = AlgoConfig(
    warmup_minutes=12,
    steep_angle_threshold=70.0,
    proximity_points=15.0,
    min_reversal_minutes=0,
    min_entry_angle=0.0,
    partial_tp_pts=50.0,
    wm_shield_distance=12.0,
    swing_anchor_threshold=10.0,
    cushion_points=0.0,
    limit_expiry_bars=5,
)

csv_files = sorted([f for f in os.listdir(_DATA_ROOT)
                    if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])

# Collect session_pl at each hour mark
end_times = ["10:00", "10:30", "11:00", "11:30", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00"]
results = {et: [] for et in end_times}

for i, fname in enumerate(csv_files):
    target_date = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
    fpath = os.path.join(_DATA_ROOT, fname)

    try:
        df = pd.read_csv(fpath, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        if len(df) < 15:
            continue
        if (df[["Open", "High", "Low", "Close"]] <= 0).any().any():
            continue
        if df["High"].max() == df["Low"].min():
            continue
        if df["Volume"].sum() < 100:
            continue

        day_start = pd.Timestamp(f"{target_date} 09:30", tz=_EST)
        day_end = pd.Timestamp(f"{target_date} 16:59", tz=_EST)
        day_data = df[(df.index >= day_start) & (df.index <= day_end)]
        if len(day_data) < 15:
            continue

        algo_df = run_trading_algo_fast(day_data, target_date, "09:30", "17:00", config=config)

        for et in end_times:
            end_ts = pd.Timestamp(f"{target_date} {et}", tz=_EST)
            sliced = algo_df[(algo_df.index >= day_start) & (algo_df.index <= end_ts)]
            if len(sliced) >= 2:
                pl = float(sliced["session_pl"].iloc[-1])
                results[et].append(pl)

    except Exception:
        continue

    if (i + 1) % 100 == 0:
        print(f"  [{i+1}/{len(csv_files)}]...", flush=True)

# Print results
print(f"\n{'='*70}", flush=True)
print(f"ENGINE 89 — FULL BACKTEST (session_pl from engine, no SL)", flush=True)
print(f"Config: warmup=12, steep=70, proximity=15, wm_shield=12, swing=10", flush=True)
print(f"{'='*70}", flush=True)
print(f"{'End Time':<10}{'Days':<7}{'Win':<7}{'Lose':<7}{'Win%':<8}{'Total Pts':<12}{'Avg/Day':<10}", flush=True)
print(f"{'-'*60}", flush=True)

for et in end_times:
    arr = np.array(results[et])
    if len(arr) == 0:
        continue
    wins = (arr > 0).sum()
    losses = (arr <= 0).sum()
    win_pct = wins / len(arr) * 100
    print(f"{et:<10}{len(arr):<7}{wins:<7}{losses:<7}{win_pct:<8.1f}{arr.sum():<+12.0f}{arr.mean():<+10.1f}", flush=True)

# Hourly incremental breakdown
print(f"\n{'='*70}", flush=True)
print(f"HOURLY INCREMENTAL P/L (how much each hour adds)", flush=True)
print(f"{'='*70}", flush=True)
print(f"{'Hour':<12}{'Incremental':<15}{'Cumulative':<15}", flush=True)
print(f"{'-'*42}", flush=True)

prev_avg = 0.0
hour_pairs = [
    ("09:30-10:00", "10:00"),
    ("10:00-10:30", "10:30"),
    ("10:30-11:00", "11:00"),
    ("11:00-11:30", "11:30"),
    ("11:30-12:00", "12:00"),
    ("12:00-13:00", "13:00"),
    ("13:00-14:00", "14:00"),
    ("14:00-15:00", "15:00"),
    ("15:00-16:00", "16:00"),
    ("16:00-17:00", "17:00"),
]

for label, et in hour_pairs:
    arr = np.array(results[et])
    if len(arr) == 0:
        continue
    cur_avg = arr.mean()
    incr = cur_avg - prev_avg
    print(f"{label:<12}{incr:<+15.1f}{cur_avg:<+15.1f}", flush=True)
    prev_avg = cur_avg

# Full day stats
print(f"\n{'='*70}", flush=True)
print(f"FULL DAY STATS (17:00 close)", flush=True)
print(f"{'='*70}", flush=True)
arr17 = np.array(results["17:00"])
print(f"Days: {len(arr17)}", flush=True)
print(f"Total pts: {arr17.sum():+.0f}", flush=True)
print(f"Avg pts/day: {arr17.mean():+.1f}", flush=True)
print(f"Median: {np.median(arr17):+.1f}", flush=True)
print(f"Win days: {(arr17 > 0).sum()} ({(arr17 > 0).sum()/len(arr17)*100:.1f}%)", flush=True)
print(f"Std dev: {arr17.std():.1f}", flush=True)
print(f"Best day: {arr17.max():+.0f}", flush=True)
print(f"Worst day: {arr17.min():+.0f}", flush=True)
cum = np.cumsum(arr17)
dd = (cum - np.maximum.accumulate(cum)).min()
print(f"Max drawdown: {dd:+.0f}", flush=True)

# Note about SL
print(f"\nNote: 60pt SL is NOT applied in these numbers.", flush=True)
print(f"Based on MAE analysis, 60pt SL adds approximately +27 pts/day.", flush=True)
print(f"Estimated with SL: {arr17.mean() + 27:+.1f} pts/day", flush=True)
