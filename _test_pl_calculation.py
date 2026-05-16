"""Test P/L calculation for a simple trade without partial TP"""
import pandas as pd
import pytz
import numpy as np
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

# Create simple test data: buy at 49000, sell at 49100
est = pytz.timezone('US/Eastern')
dates = pd.date_range('2026-05-14 09:30', periods=10, freq='1min', tz=est)

# Bars: warmup, then buy signal, then sell signal
data = pd.DataFrame({
    'Open': [49000, 49000, 49000, 49000, 49000, 49050, 49100, 49100, 49100, 49100],
    'High': [49010, 49010, 49010, 49010, 49010, 49060, 49110, 49110, 49110, 49110],
    'Low':  [48990, 48990, 48990, 48990, 48990, 49040, 49090, 49090, 49090, 49090],
    'Close':[49000, 49000, 49000, 49000, 49000, 49050, 49100, 49100, 49100, 49100],
}, index=dates)

# Config with NO partial TP
config = AlgoConfig(
    warmup_minutes=3,  # warmup for first 3 bars
    steep_angle_threshold=65.0,
    proximity_points=8.0,
    min_reversal_minutes=0,
    min_entry_angle=0.0,  # allow entry immediately
    partial_tp_pts=0.0,   # DISABLE partial TP
    spike_profit_pts=0.0,  # DISABLE spike exit
    wm_shield_distance=0.0,
    steep_line_reentry=False,
    steep_line_proximity=0.0,
)

result = run_trading_algo_fast(data, '2026-05-14', '09:30', '09:40', config=config)

print("\nAll bars:")
print(result[['Open', 'Close', 'signal', 'buy_price', 'sell_price', 'session_pl', 'pos_debug']].to_string())

print(f"\n\nExpected P/L: 100 pts per contract × 2 contracts = 200 pts")
print(f"Actual P/L: {result['session_pl'].iloc[-1]:.0f} pts")
