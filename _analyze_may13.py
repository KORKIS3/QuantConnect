"""Analyze May 13 signals and P/L"""
import pandas as pd
import pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

# Load May 13 data
fpath = r'C:\Users\Administrator\Desktop\IB_Live\tracking\YM_tracking_DUO158495_2026-05-13_0930.csv'
df = pd.read_csv(fpath, index_col=0, parse_dates=True)
est = pytz.timezone('US/Eastern')
df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)

# Filter to 9:30-16:00
day_start = pd.Timestamp('2026-05-13 09:30', tz=est)
day_end = pd.Timestamp('2026-05-13 16:00', tz=est)
df = df[(df.index >= day_start) & (df.index <= day_end)]

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
    steep_line_proximity=0.0,
)

result = run_trading_algo_fast(df, '2026-05-13', '09:30', '16:00', config=config)

# Show all signals
signals = result[result['signal'] != ''].copy()
print('\nAll signals:')
print(signals[['signal', 'buy_price', 'sell_price', 'is_liquidation', 'partial_tp', 'session_pl']].to_string())

# Show bar 25 specifically (09:54)
print('\n\nBar 25 (09:54) details:')
bar25 = result.iloc[24:26]
print(bar25[['Open', 'High', 'Low', 'Close', 'signal', 'buy_price', 'sell_price', 'is_liquidation', 'partial_tp', 'session_pl', 'pos_debug']])

print(f'\n\nFinal P/L: {result["session_pl"].iloc[-1]:.1f} pts')
print(f'Final position: {result["pos_debug"].iloc[-1]} (0=flat, 1=long, 2=short)')
