"""Trace position changes from 09:42 to 09:47 on May 12, 2026"""
import pandas as pd
import pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

# Load May 12 data
fpath = r"C:\Users\Administrator\Desktop\2YearsData\full_day\CBOT_MINI_YM1_2026-05-12.csv"
df = pd.read_csv(fpath, index_col=0, parse_dates=True)
est = pytz.timezone("US/Eastern")
df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)

# Config from commit 8a15b10
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
    steep_line_proximity=0.0,
    steep_line_exit_only=False,
)

# Run algo
result = run_trading_algo_fast(
    df, 
    target_date="2026-05-12",
    start_time="09:30",
    end_time="17:00",
    config=config
)

# Filter to 09:40-09:50
start = pd.Timestamp("2026-05-12 09:40", tz=est)
end = pd.Timestamp("2026-05-12 09:50", tz=est)
window = result[(result.index >= start) & (result.index <= end)]

# Print relevant columns
print("\nAvailable columns:")
print(result.columns.tolist())
print("\nBars from 09:40 to 09:50:")
print("="*120)
print(window.to_string())
print("="*120)
