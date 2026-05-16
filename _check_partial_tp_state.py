"""Check if partial_tp_exit_price has stale values"""
import pandas as pd
import pytz
from pathlib import Path
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig

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

# Check all partial TP events
partial_tps = result[result['partial_tp'] == True].copy()

print("All Partial TP events:")
print("="*80)

for idx, row in partial_tps.iterrows():
    time_str = idx.strftime('%H:%M')
    print(f"{time_str}: Partial TP @ {row['Close']:.0f}, Position: {row['position']}")

# Check trades around partial TPs
trades = result[result['signal'].isin(['BUY', 'SELL'])].copy()

print("\n\nAll trades:")
print("="*80)

for idx, row in trades.iterrows():
    time_str = idx.strftime('%H:%M')
    signal_price = row['buy_price'] if row['signal'] == 'BUY' else row['sell_price']
    print(f"{time_str}: {row['signal']} @ {signal_price:.0f}, Partial TP: {row['partial_tp']}, Session P/L: {row['session_pl']:.1f}")
