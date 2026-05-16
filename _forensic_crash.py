"""Forensic audit: trace the exact crash with warmup_minutes=35 on CBOT_MINI_YM1_2023-10-31.csv"""
import sys, os, faulthandler
faulthandler.enable()
sys.path.insert(0, '.')

import pandas as pd, pytz, numpy as np
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

# This file crashed with heap corruption (0xc0000374) at line 1404
fname = "CBOT_MINI_YM1_2023-10-31.csv"
fpath = os.path.join(DATA_ROOT, fname)

df = pd.read_csv(fpath, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(EST)

day_start = pd.Timestamp("2023-10-31 09:30", tz=EST)
day_end = pd.Timestamp("2023-10-31 16:59", tz=EST)
day_data = df[(df.index >= day_start) & (df.index <= day_end)]

print("=" * 80)
print("FORENSIC AUDIT: Crash on CBOT_MINI_YM1_2023-10-31.csv")
print("=" * 80)

# 8. Shape and type of all inputs
print(f"\n[INPUT DATA]")
print(f"  Shape: {day_data.shape}")
print(f"  Index dtype: {day_data.index.dtype}")
print(f"  Columns: {list(day_data.columns)}")
print(f"  dtypes: {dict(day_data.dtypes)}")
print(f"  First index: {day_data.index[0]}")
print(f"  Last index: {day_data.index[-1]}")
print(f"  Total bars: {len(day_data)}")

# Data quality
print(f"\n[DATA QUALITY]")
print(f"  Volume sum: {day_data['Volume'].sum()}")
print(f"  Bars with volume > 0: {(day_data['Volume'] > 0).sum()}")
print(f"  High max: {day_data['High'].max()}")
print(f"  Low min: {day_data['Low'].min()}")
print(f"  Price range: {day_data['High'].max() - day_data['Low'].min()}")
print(f"  Unique Close values: {day_data['Close'].nunique()}")
print(f"  Bars where Open==High==Low==Close: {((day_data['Open']==day_data['High']) & (day_data['High']==day_data['Low']) & (day_data['Low']==day_data['Close'])).sum()}")

# 10. Which parameter changed
print(f"\n[PARAMETER UNDER TEST]")
print(f"  warmup_minutes=5 (baseline) -> does NOT crash")
print(f"  warmup_minutes=35 (test) -> crashes")
print(f"  All other parameters identical")

# 9. Whether the crash appeared immediately after parameter changes
print(f"\n[CRASH TIMING]")
print(f"  Crash occurs on FIRST call to run_trading_algo_fast with this file")
print(f"  Not cumulative — isolated subprocess also crashes")

# Test with warmup=5 first to confirm it works
print(f"\n[TEST: warmup_minutes=5]")
config5 = AlgoConfig(
    warmup_minutes=5,
    steep_angle_threshold=65.0,
    proximity_points=8.0,
    min_reversal_minutes=0,
    min_entry_angle=15.0,
    partial_tp_pts=50.0,
    spike_profit_pts=50.0,
    spike_profit_bars=9,
    wm_shield_distance=0.0,
    steep_line_reentry=False,
    steep_line_proximity=0.0,
    steep_line_exit_only=False,
)
try:
    result5 = run_trading_algo_fast(day_data, "2023-10-31", "09:30", "17:00", config=config5)
    print(f"  Result: SUCCESS")
    print(f"  Output shape: {result5.shape}")
    print(f"  Output columns: {list(result5.columns)}")
except Exception as e:
    print(f"  Result: EXCEPTION: {type(e).__name__}: {e}")

# Now test with warmup=35
print(f"\n[TEST: warmup_minutes=35]")
print(f"  About to call run_trading_algo_fast...")
print(f"  If no output follows, process died from heap corruption.")
sys.stdout.flush()

config35 = AlgoConfig(
    warmup_minutes=35,
    steep_angle_threshold=65.0,
    proximity_points=8.0,
    min_reversal_minutes=0,
    min_entry_angle=15.0,
    partial_tp_pts=50.0,
    spike_profit_pts=50.0,
    spike_profit_bars=9,
    wm_shield_distance=0.0,
    steep_line_reentry=False,
    steep_line_proximity=0.0,
    steep_line_exit_only=False,
)
try:
    result35 = run_trading_algo_fast(day_data, "2023-10-31", "09:30", "17:00", config=config35)
    print(f"  Result: SUCCESS")
    print(f"  Output shape: {result35.shape}")
except Exception as e:
    print(f"  Result: EXCEPTION: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

print("\n[END OF AUDIT]")
