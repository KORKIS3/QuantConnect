"""Test P/L calculation on a single day"""
import pandas as pd
import pytz
from pathlib import Path
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig

# Test on May 8
data_path = Path.home() / "Desktop" / "2YearsData" / "full_day" / "CBOT_MINI_YM1_2026-05-08.csv"
df = pd.read_csv(data_path, index_col=0, parse_dates=True)

est = pytz.timezone("US/Eastern")
df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)

config = AlgoConfig(
    warmup_minutes=5,
    steep_angle_threshold=65.0,
    proximity_points=8.0,
    min_reversal_minutes=0,
    min_entry_angle=15.0,
    partial_tp_pts=50.0,
    num_contracts=2,
)

result = run_trading_algo_fast(df, "2026-05-08", "09:30", "17:00", config)

# Find all trades
trades = result[result['signal'].isin(['BUY', 'SELL'])].copy()

print(f"May 8, 2026 - Trade Analysis")
print(f"{'='*80}")

for idx, row in trades.iterrows():
    time_str = idx.strftime('%H:%M')
    print(f"\n{time_str}: {row['signal']} @ {row['buy_price'] if row['signal'] == 'BUY' else row['sell_price']:.0f}")
    print(f"  Position after: {row['position']}")
    print(f"  Session P/L: {row['session_pl']:.1f} pts")
    print(f"  Liquidation: {row['is_liquidation']}")
    print(f"  Partial TP: {row['partial_tp']}")

final_pl = result.iloc[-1]['session_pl']
final_pos = result.iloc[-1]['position']
final_close = result.iloc[-1]['Close']
last_entry_price = None

# Find the last entry price
for idx, row in trades[::-1].iterrows():
    if row['position'] != 0:
        if row['signal'] == 'BUY':
            last_entry_price = row['buy_price']
        else:
            last_entry_price = row['sell_price']
        break

print(f"\n{'='*80}")
print(f"Final session P/L (from column): {final_pl:.1f} pts")
print(f"Final position: {final_pos}")
print(f"Final close: {final_close:.0f}")
print(f"Last entry price: {last_entry_price:.0f}" if last_entry_price else "Last entry price: None")

if final_pos != 0 and last_entry_price:
    unrealized = (final_close - last_entry_price) if final_pos == 1 else (last_entry_price - final_close)
    print(f"Unrealized P/L: {unrealized:.1f} pts")
    print(f"Total P/L (realized + unrealized): {final_pl + unrealized:.1f} pts")
    print(f"\n⚠ WARNING: session_pl column doesn't include unrealized P/L!")
else:
    print(f"\n✓ Position flat at end of session")
