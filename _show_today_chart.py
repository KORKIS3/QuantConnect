"""Interactive chart for today's session"""
import os
import pandas as pd
import pytz
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig
from plotFigure import plot_intraday_data

_EST = pytz.timezone("US/Eastern")
_IB_LIVE_ROOT = os.path.expanduser("~/Desktop/IB_Live")

# Find today's tracking file
tracking_dir = os.path.join(_IB_LIVE_ROOT, "tracking")
files = sorted([f for f in os.listdir(tracking_dir) if f.startswith("YM_tracking_") and f.endswith(".csv")])
if not files:
    print("No tracking files found")
    exit(1)

latest_file = files[-1]
print(f"Loading: {latest_file}")

# Extract date from filename: YM_tracking_DUO158495_2026-05-14_0930.csv
date_str = latest_file.split("_")[3]  # "2026-05-14"
print(f"Date: {date_str}")

# Load data
fpath = os.path.join(tracking_dir, latest_file)
df = pd.read_csv(fpath, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)

print(f"Loaded {len(df)} bars from {df.index[0]} to {df.index[-1]}")

# Run algo with current config
config = AlgoConfig(
    warmup_minutes=12,
    steep_angle_threshold=70.0,
    proximity_points=15.0,
    min_reversal_minutes=0,
    min_entry_angle=0.0,
    partial_tp_pts=50.0,
    spike_profit_pts=100.0,
    spike_profit_bars=9,
    wm_shield_distance=12.0,
    steep_line_reentry=False,
    steep_line_proximity=5.0,
    steep_line_exit_only=False,
    num_contracts=2,
)

result = run_trading_algo_fast(df, date_str, "09:30", "17:00", config=config)

if result is not None and len(result) > 0:
    final_pl = result["session_pl"].iloc[-1]
    print(f"\nSession final P/L: {final_pl:.0f} pts")
    
    # Count TP events
    if "partial_tp" in result.columns:
        tp_count = result["partial_tp"].sum()
        print(f"Partial TP events: {tp_count}")
    
    # Launch interactive chart
    print("\nLaunching interactive chart...")
    plot_intraday_data(result, date_str, "09:30", "17:00")
    print("Chart closed.")
else:
    print("No result generated")
