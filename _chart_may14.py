"""Interactive chart for May 14, 2026"""
from datetime import datetime
import pytz
from pathlib import Path
import pandas as pd
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast
from plotFigure import plot_intraday_data

# May 14, 2026
est = pytz.timezone('US/Eastern')
date_str = '2026-05-14'

print(f"Loading data for {date_str}...")

# Load data
csv_path = Path.home() / "Desktop" / "2YearsData" / "full_day" / f"CBOT_MINI_YM1_{date_str}.csv"

if not csv_path.exists():
    print(f"ERROR: File not found: {csv_path}")
    print(f"Trying IB_Live tracking folder...")
    csv_path = Path.home() / "Desktop" / "IB_Live" / "tracking" / f"YM_tracking_DUO158495_{date_str}_0930.csv"
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

# Config - current live settings
config = AlgoConfig(
    warmup_minutes=7,
    steep_angle_threshold=90.0,
    proximity_points=4.0,
    min_reversal_minutes=0,
    min_entry_angle=0.0,
    partial_tp_pts=50.0,
    spike_profit_pts=50.0,
    spike_profit_bars=9,
    wm_shield_distance=0.0,
    steep_line_reentry=False,
    steep_line_proximity=0.0,  # Live uses 0.0
    steep_line_exit_only=False,
    num_contracts=2,
)

# Run algo
result = run_trading_algo_fast(df, target_date=date_str, start_time="09:30", end_time="17:00", config=config)

# Show final P/L
final_pl = result.iloc[-1]['session_pl']
print(f"\nDay session final P/L: {final_pl:.0f} pts (2 contracts)")

# Count trades
buy_signals = result[result['signal'] == 'BUY']
sell_signals = result[result['signal'] == 'SELL']
print(f"Trades: {len(buy_signals)} BUY, {len(sell_signals)} SELL")

# Plot interactive chart
plot_intraday_data(result, date_str, "09:30", "17:00")
