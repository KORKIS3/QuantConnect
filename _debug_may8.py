"""Debug May 8 algo run"""
import pytz
from pathlib import Path
import pandas as pd
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

est = pytz.timezone('US/Eastern')
date_str = '2026-05-08'

print(f"Loading data for {date_str}...")

csv_path = Path.home() / "Desktop" / "2YearsData" / "full_day" / f"CBOT_MINI_YM1_{date_str}.csv"
df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)

print(f"Total bars loaded: {len(df)}")

# Filter to day session
day_start = pd.Timestamp(f"{date_str} 09:30", tz=est)
day_end = pd.Timestamp(f"{date_str} 17:00", tz=est)
df = df[(df.index >= day_start) & (df.index <= day_end)]

print(f"Day session bars (9:30-17:00): {len(df)}")

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

# Check P/L
print(f"\nP/L:")
print(f"  session_pl range: {result['session_pl'].min():.0f} to {result['session_pl'].max():.0f}")
print(f"  Final session_pl: {result.iloc[-1]['session_pl']:.0f}")

# Check signal column
print(f"\nSignal column unique values: {result['signal'].unique()}")
print(f"Signal column dtype: {result['signal'].dtype}")

# Count actual numeric signals
numeric_signals = pd.to_numeric(result['signal'], errors='coerce')
buys = (numeric_signals == 1).sum()
sells = (numeric_signals == -1).sum()
zeros = (numeric_signals == 0).sum()
nans = numeric_signals.isna().sum()

print(f"\nSignal counts:")
print(f"  BUY (1): {buys}")
print(f"  SELL (-1): {sells}")
print(f"  FLAT (0): {zeros}")
print(f"  NaN/invalid: {nans}")
