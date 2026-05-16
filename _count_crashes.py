"""Count how many days crash vs succeed"""
import os
import pandas as pd
import pytz
from pathlib import Path
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

DATA_ROOT = Path.home() / "Desktop" / "2YearsData" / "full_day"
csv_files = sorted([f for f in os.listdir(DATA_ROOT) if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])

print(f"Testing {len(csv_files)} days...")
print("="*80)

success_count = 0
crash_count = 0
crash_days = []

config = AlgoConfig(
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
    steep_line_proximity=5.0,
    num_contracts=2,
)

for idx, fname in enumerate(csv_files):
    date_str = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
    csv_path = DATA_ROOT / fname
    
    try:
        df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
        est = pytz.timezone('US/Eastern')
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)
        
        day_start = pd.Timestamp(f"{date_str} 09:30", tz=est)
        day_end = pd.Timestamp(f"{date_str} 17:00", tz=est)
        df = df[(df.index >= day_start) & (df.index <= day_end)]
        
        if len(df) < 15:
            continue
        
        result = run_trading_algo_fast(df, target_date=date_str, start_time="09:30", end_time="17:00", config=config)
        success_count += 1
        
    except Exception as e:
        crash_count += 1
        crash_days.append((date_str, str(e)))
        if crash_count <= 10:  # Show first 10 crashes
            print(f"CRASH: {date_str} - {str(e)[:80]}")
    
    if (idx + 1) % 50 == 0:
        print(f"Progress: {idx+1}/{len(csv_files)} - Success: {success_count}, Crashes: {crash_count}")

print("\n" + "="*80)
print("RESULTS")
print("="*80)
print(f"Total days tested: {len(csv_files)}")
print(f"Successful: {success_count} ({success_count/len(csv_files)*100:.1f}%)")
print(f"Crashed: {crash_count} ({crash_count/len(csv_files)*100:.1f}%)")

if crash_days:
    print(f"\nFirst 10 crash days:")
    for date_str, error in crash_days[:10]:
        print(f"  {date_str}: {error[:60]}")
