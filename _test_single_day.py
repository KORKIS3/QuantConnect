"""Test single day after cache clear"""
import pandas as pd
import pytz
from pathlib import Path
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

# Load one day
date_str = "2024-01-02"
csv_path = Path.home() / "Desktop" / "2YearsData" / "full_day" / f"CBOT_MINI_YM1_{date_str}.csv"

print(f"Loading: {csv_path}")
df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
est = pytz.timezone('US/Eastern')
df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)

# Filter to day session
day_start = pd.Timestamp(f"{date_str} 09:30", tz=est)
day_end = pd.Timestamp(f"{date_str} 17:00", tz=est)
df = df[(df.index >= day_start) & (df.index <= day_end)]

print(f"Bars: {len(df)}")

# Run algo
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

try:
    result = run_trading_algo_fast(df, target_date=date_str, start_time="09:30", end_time="17:00", config=config)
    
    final_pl = result.iloc[-1]['session_pl']
    buy_signals = result[result['signal'] == 'BUY']
    sell_signals = result[result['signal'] == 'SELL']
    
    print(f"\nRESULTS:")
    print(f"  Final P/L: {final_pl:.1f} pts")
    print(f"  BUY signals: {len(buy_signals)}")
    print(f"  SELL signals: {len(sell_signals)}")
    
except Exception as e:
    print(f"\nERROR: {e}")
    import traceback
    traceback.print_exc()
