"""Interactive chart for yesterday"""
from datetime import datetime, timedelta
import pytz
from pathlib import Path
import pandas as pd
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast
from plotFigure import plot_intraday_data

# Get yesterday's date
est = pytz.timezone('US/Eastern')
today = datetime(2026, 5, 12, tzinfo=est)
yesterday = today - timedelta(days=1)
date_str = yesterday.strftime('%Y-%m-%d')

print(f"Loading data for {date_str}...")

# Load data
csv_path = Path.home() / "Desktop" / "2YearsData" / "full_day" / f"CBOT_MINI_YM1_{date_str}.csv"

if not csv_path.exists():
    print(f"ERROR: File not found: {csv_path}")
    exit(1)

df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)

# Filter to day session
day_start = pd.Timestamp(f"{date_str} 09:30", tz=est)
day_end = pd.Timestamp(f"{date_str} 17:00", tz=est)
df = df[(df.index >= day_start) & (df.index <= day_end)]

print(f"Day session bars: {len(df)} (9:30-17:00)")

# Config
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
    steep_line_exit_only=False,
)

# Run algo
result = run_trading_algo_fast(df, target_date=date_str, start_time="09:30", end_time="17:00", config=config)

# Show final P/L
final_pl = result.iloc[-1]['session_pl']
print(f"\nDay session final P/L: {final_pl:.0f} pts")

# Plot interactive chart
plot_intraday_data(result, date_str, "09:30", "17:00")
