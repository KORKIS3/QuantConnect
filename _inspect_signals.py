"""Inspect what's actually in the signal column"""
import pandas as pd
import pytz
from pathlib import Path
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

date_str = "2024-01-02"
csv_path = Path.home() / "Desktop" / "2YearsData" / "full_day" / f"CBOT_MINI_YM1_{date_str}.csv"

df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
est = pytz.timezone('US/Eastern')
df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)

day_start = pd.Timestamp(f"{date_str} 09:30", tz=est)
day_end = pd.Timestamp(f"{date_str} 17:00", tz=est)
df = df[(df.index >= day_start) & (df.index <= day_end)]

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

result = run_trading_algo_fast(df, target_date=date_str, start_time="09:30", end_time="17:00", config=config)

print("=== SIGNAL COLUMN ANALYSIS ===\n")
print(f"Total rows: {len(result)}")
print(f"Signal column type: {result['signal'].dtype}")
print(f"Unique values in signal column: {result['signal'].unique()}")
print(f"Value counts:")
print(result['signal'].value_counts())

print("\n=== ACTUAL BUY/SELL SIGNALS ===")
buy_sell = result[result['signal'].isin(['BUY', 'SELL'])]
print(f"Total BUY/SELL signals: {len(buy_sell)}")

for idx, row in buy_sell.iterrows():
    print(f"{idx}: {row['signal']} @ {row['Close']:.0f}, position={row['position']}, pl={row['session_pl']:.1f}")

print("\n=== P/L PROGRESSION ===")
pl_changes = result[result['session_pl'].diff() != 0]
print(f"P/L changed {len(pl_changes)} times")
for idx, row in pl_changes.head(20).iterrows():
    print(f"{idx}: signal={row['signal']}, pl={row['session_pl']:.1f}, position={row['position']}")
