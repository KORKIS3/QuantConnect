"""Compare cushion=0 vs cushion=40 vs actual IB fills for June 4."""
import pandas as pd, pytz, sys
sys.path.insert(0, '.')
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

_EST = pytz.timezone('US/Eastern')

df = pd.read_csv(
    r'C:\Users\Administrator\Desktop\IB_Live\tracking\YM_tracking_DUO158495_2026-06-04_0930.csv',
    index_col=0, parse_dates=True
)
ohlcv = df[['Open','High','Low','Close','Volume']].copy()

# cushion=0
cfg0 = AlgoConfig(warmup_minutes=7, steep_angle_threshold=90.0, proximity_points=4.0,
    min_reversal_minutes=0, min_entry_angle=0.0, partial_tp_pts=50.0,
    spike_profit_pts=100.0, spike_profit_bars=9, wm_shield_distance=0.0,
    swing_anchor_threshold=10.0, cushion_points=0.0, limit_expiry_bars=5)
algo0 = run_trading_algo_fast(ohlcv, '2026-06-04', '09:30', '17:00', config=cfg0)
trades0 = algo0[algo0['signal'].isin(['BUY','SELL'])]

# cushion=40
cfg40 = AlgoConfig(warmup_minutes=7, steep_angle_threshold=90.0, proximity_points=4.0,
    min_reversal_minutes=0, min_entry_angle=0.0, partial_tp_pts=50.0,
    spike_profit_pts=100.0, spike_profit_bars=9, wm_shield_distance=0.0,
    swing_anchor_threshold=10.0, cushion_points=40.0, limit_expiry_bars=5)
algo40 = run_trading_algo_fast(ohlcv, '2026-06-04', '09:30', '17:00', config=cfg40)
trades40 = algo40[algo40['signal'].isin(['BUY','SELL'])]

print("=== IB ACTUAL FILLS (from logs) ===")
print("  10:13 BOT 2 @ 51502")
print("  10:24 SLD 2 @ 51547")
print("  11:17 SLD 2 @ 51641")
print("  11:41 BOT 2 @ 51618")
print("  Total: 4 fills")
print()

print("=== BACKTEST cushion=0 (instant fill) ===")
for ts, row in trades0.iterrows():
    sig = row['signal']
    price = row['buy_price'] if sig == 'BUY' else row['sell_price']
    print(f"  {ts.strftime('%H:%M')} {sig} @ {price:.0f}")
print(f"  Total: {len(trades0)} trades")
print()

print("=== BACKTEST cushion=40 (limit order sim) ===")
for ts, row in trades40.iterrows():
    sig = row['signal']
    price = row['buy_price'] if sig == 'BUY' else row['sell_price']
    print(f"  {ts.strftime('%H:%M')} {sig} @ {price:.0f}")
print(f"  Total: {len(trades40)} trades")
