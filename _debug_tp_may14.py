"""Debug: why didn't partial TP trigger at 9:59 on May 14?"""
import sys; sys.path.insert(0, '.')
import pandas as pd, pytz
from pathlib import Path
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

est = pytz.timezone('US/Eastern')
date_str = '2026-05-14'

csv_path = Path.home() / "Desktop" / "IB_Live" / "tracking" / f"YM_tracking_DUO158495_{date_str}_0930.csv"
df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)

day_start = pd.Timestamp(f"{date_str} 09:30", tz=est)
day_end = pd.Timestamp(f"{date_str} 17:00", tz=est)
df = df[(df.index >= day_start) & (df.index <= day_end)]

config = AlgoConfig(
    warmup_minutes=8,
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
    steep_line_exit_only=False,
    num_contracts=2,
)

result = run_trading_algo_fast(df, target_date=date_str, start_time="09:30", end_time="17:00", config=config)

# Find the BUY at ~9:49 at 50055
print("=== SIGNALS 9:38-10:05 ===")
window = result[(result.index >= pd.Timestamp(f"{date_str} 09:38", tz=est)) & 
                (result.index <= pd.Timestamp(f"{date_str} 10:05", tz=est))]

for idx, row in window.iterrows():
    sig = row.get('signal', '')
    tp = row.get('partial_tp', False)
    pl = row.get('session_pl', 0)
    close = row['Close']
    high = row['High']
    extra = ""
    if sig and sig != '':
        extra = f"  *** SIGNAL: {sig} @ {row.get('signal_price', close):.0f} ***"
    if tp:
        extra += f"  *** PARTIAL TP ***"
    print(f"  {idx.strftime('%H:%M')} | C={close:.0f} H={high:.0f} | PL={pl:.0f}{extra}")

# Specifically check the BUY at 50055
print("\n=== ENTRY ANALYSIS ===")
buys = result[result['signal'] == 'BUY']
print(f"All BUY signals:")
for idx, row in buys.iterrows():
    print(f"  {idx.strftime('%H:%M:%S')} @ {row.get('signal_price', row['Close']):.0f}")

# Check bars 9:49-10:00 for TP condition
print("\n=== TP CHECK: entry at 50055, need close >= 50105 ===")
check = result[(result.index >= pd.Timestamp(f"{date_str} 09:49", tz=est)) & 
               (result.index <= pd.Timestamp(f"{date_str} 10:02", tz=est))]
for idx, row in check.iterrows():
    close = row['Close']
    high = row['High']
    unrealized = close - 50055
    print(f"  {idx.strftime('%H:%M')} | Close={close:.0f} High={high:.0f} | unrealized={unrealized:.0f} pts {'<-- TP!' if unrealized >= 50 else ''}")
