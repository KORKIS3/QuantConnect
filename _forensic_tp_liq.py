"""FORENSIC AUDIT: TP and LIQ firing on same bar at same price.
Trace the exact execution path to find why partial TP doesn't reduce position."""
import sys, os
sys.path.insert(0, '.')
import pandas as pd, pytz, numpy as np
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

EST = pytz.timezone("US/Eastern")
csv_path = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "tracking", "YM_tracking_DUO158495_2026-05-14_0930.csv")

df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(EST)
day_start = pd.Timestamp("2026-05-14 09:30", tz=EST)
day_end = pd.Timestamp("2026-05-14 17:00", tz=EST)
df = df[(df.index >= day_start) & (df.index <= day_end)]

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
    steep_line_proximity=0.0,
    steep_line_exit_only=False,
    num_contracts=2,
)

result = run_trading_algo_fast(df, "2026-05-14", "09:30", "17:00", config=config)

# Find all bars where BOTH partial_tp AND liquidate are True
print("=" * 80)
print("FORENSIC AUDIT: TP + LIQ on same bar")
print("=" * 80)

# First, find all TP events
tp_bars = result[result['partial_tp'] == True]
print(f"\nTotal TP events: {len(tp_bars)}")

# Find all LIQ events
liq_bars = result[result['is_liquidation'] == True]
print(f"Total LIQ events: {len(liq_bars)}")

# Find overlaps
overlap = result[(result['partial_tp'] == True) & (result['is_liquidation'] == True)]
print(f"TP + LIQ on SAME bar: {len(overlap)}")

if len(overlap) > 0:
    print(f"\nOverlap bars:")
    for idx, row in overlap.iterrows():
        print(f"  {idx.strftime('%H:%M')} | Close={row['Close']:.0f} | Signal={row['signal']} | PL={row['session_pl']:.0f}")

# Now trace ALL signals with TP and LIQ context
print(f"\n{'='*80}")
print("FULL SIGNAL TRACE (signals + TP + LIQ)")
print("=" * 80)

events = result[(result['signal'].isin(['BUY', 'SELL'])) | (result['partial_tp'] == True) | (result['is_liquidation'] == True)]
for idx, row in events.iterrows():
    parts = []
    if row['signal'] in ['BUY', 'SELL']:
        parts.append(f"SIGNAL:{row['signal']}")
    if row['partial_tp']:
        parts.append("TP")
    if row['is_liquidation']:
        parts.append("LIQ")
    print(f"  {idx.strftime('%H:%M')} | C={row['Close']:.0f} | {' + '.join(parts)} | PL={row['session_pl']:.0f}")

# Now check: what does the signal loop do when TP fires?
# The key question: after TP fires, does the position go from 2->1 or does it exit entirely?
print(f"\n{'='*80}")
print("POSITION TRACE (pos_debug column)")
print("=" * 80)

# Check if pos_debug exists
if 'pos_debug' in result.columns:
    # Show position around TP events
    for tp_idx in tp_bars.index:
        window_start = tp_idx - pd.Timedelta(minutes=2)
        window_end = tp_idx + pd.Timedelta(minutes=2)
        window = result[(result.index >= window_start) & (result.index <= window_end)]
        print(f"\n  Around TP at {tp_idx.strftime('%H:%M')}:")
        for idx, row in window.iterrows():
            marker = " <-- TP" if idx == tp_idx else ""
            liq_mark = " <-- LIQ" if row.get('is_liquidation', False) else ""
            sig_mark = f" <-- {row['signal']}" if row['signal'] in ['BUY', 'SELL'] else ""
            print(f"    {idx.strftime('%H:%M')} | pos={row['pos_debug']:+d} | C={row['Close']:.0f} | PL={row['session_pl']:.0f}{marker}{liq_mark}{sig_mark}")
else:
    print("  pos_debug column not found!")
