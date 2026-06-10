"""Run the EXACT engine from commit 83fcb35 (Cushion of 40 points) with the live config.
This is what was tested and approved before going live.
Compare against current engine to find the discrepancy.
"""
import os, sys, importlib.util
import pandas as pd
import numpy as np
import pytz

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

# Load old engine from the cushion commit
spec = importlib.util.spec_from_file_location("cushion_engine", "TradingAlgoFast_cushion_commit.py")
old_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old_mod)

OldAlgoConfig = old_mod.AlgoConfig
old_run = old_mod.run_trading_algo_fast

# The config that was used when going live (from InteractiveBrokers.py at that commit)
old_config = OldAlgoConfig(
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

        algo_df = old_run(day_data, target_date, "09:30", "17:00", config=old_config)

        end_ts = pd.Timestamp(f"{target_date} 17:00", tz=_EST)
        sliced = algo_df[(algo_df.index >= day_start) & (algo_df.index <= end_ts)]
        if len(sliced) < 2:
            continue

        pl = float(sliced["session_pl"].iloc[-1])
        daily_pls.append(pl)

    except Exception:
        continue

    if (i + 1) % 100 == 0:
        print(f"  [{i+1}/{len(csv_files)}] {len(daily_pls)} days...", flush=True)

arr = np.array(daily_pls)

print(f"\n{'='*60}", flush=True)
print(f"COMMIT 83fcb35 ENGINE (what you deployed live)", flush=True)
print(f"Config: warmup=7, steep=90, proximity=4, wm_shield=0,", flush=True)
print(f"        swing_anchor=10, spike=100/9, partial_tp=50", flush=True)
print(f"{'='*60}", flush=True)
print(f"Days: {len(arr)}", flush=True)
print(f"Total pts: {arr.sum():+.0f}", flush=True)
print(f"Avg pts/day: {arr.mean():+.1f}", flush=True)
print(f"Win days: {(arr > 0).sum()} ({(arr > 0).sum()/len(arr)*100:.1f}%)", flush=True)
print(f"Lose days: {(arr < 0).sum()} ({(arr < 0).sum()/len(arr)*100:.1f}%)", flush=True)
print(f"Best day: {arr.max():+.0f}", flush=True)
print(f"Worst day: {arr.min():+.0f}", flush=True)
cum = np.cumsum(arr)
dd = (cum - np.maximum.accumulate(cum)).min()
print(f"Max drawdown: {dd:+.0f}", flush=True)
