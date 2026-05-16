"""FORENSIC AUDIT: What EXACTLY happens on TP+LIQ bars.
No fixes. Evidence only. Trace the exact state transitions."""
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

print("=" * 90)
print("FORENSIC AUDIT: TP and LIQ behavior on May 14, 2026")
print("Current code state (reverted, no tp_just_fired)")
print("=" * 90)

# Find all events
tp_bars = result[result['partial_tp'] == True]
liq_bars = result[result['is_liquidation'] == True]
sig_bars = result[result['signal'].isin(['BUY', 'SELL'])]

print(f"\nTotal TP events: {len(tp_bars)}")
print(f"Total LIQ events: {len(liq_bars)}")
print(f"Total signal events: {len(sig_bars)}")
print(f"TP + LIQ same bar: {len(result[(result['partial_tp']==True) & (result['is_liquidation']==True)])}")

# For each TP event, show:
# - What position was BEFORE TP
# - What position is AFTER TP (same bar end)
# - Whether a signal also fired on same bar
# - What the signal direction is vs the position direction
print(f"\n{'='*90}")
print("DETAILED TP EVENT TRACE")
print(f"{'='*90}")

for tp_idx in tp_bars.index:
    # Get bar before, TP bar, bar after
    tp_pos = tp_idx
    all_idx = result.index.tolist()
    bar_num = all_idx.index(tp_pos)
    
    prev_bar = result.iloc[bar_num - 1] if bar_num > 0 else None
    tp_bar = result.loc[tp_pos]
    next_bar = result.iloc[bar_num + 1] if bar_num < len(result) - 1 else None
    
    pos_before = prev_bar['pos_debug'] if prev_bar is not None else "N/A"
    pos_after = tp_bar['pos_debug']
    
    signal_on_bar = tp_bar['signal'] if tp_bar['signal'] in ['BUY', 'SELL'] else "NONE"
    is_liq = tp_bar['is_liquidation']
    
    # Determine if position REVERSED on this bar
    pos_next = next_bar['pos_debug'] if next_bar is not None else "N/A"
    
    print(f"\n  TP at {tp_pos.strftime('%H:%M')} | Close={tp_bar['Close']:.0f}")
    print(f"    pos BEFORE (prev bar): {pos_before}")
    print(f"    pos AFTER  (this bar): {pos_after}")
    print(f"    pos NEXT   (next bar): {pos_next}")
    print(f"    Signal on this bar: {signal_on_bar}")
    print(f"    is_liquidation: {is_liq}")
    print(f"    session_pl: {tp_bar['session_pl']:.0f}")
    
    if signal_on_bar != "NONE":
        # This is the problem case
        if pos_before == 1 and signal_on_bar == "SELL":
            print(f"    >>> ISSUE: Was LONG, TP fired, then SELL on same bar")
            print(f"    >>> Position went from LONG to {pos_after} (should stay LONG with 1 contract)")
        elif pos_before == 2 and signal_on_bar == "BUY":
            print(f"    >>> ISSUE: Was SHORT, TP fired, then BUY on same bar")
            print(f"    >>> Position went from SHORT to {pos_after} (should stay SHORT with 1 contract)")

# Show the FULL signal sequence with position
print(f"\n{'='*90}")
print("FULL CHRONOLOGICAL EVENT LOG")
print(f"{'='*90}")
print(f"{'Time':<8} {'Pos':<5} {'Event':<20} {'Close':<8} {'PL':<8}")
print("-" * 60)

events = result[(result['signal'].isin(['BUY', 'SELL'])) | (result['partial_tp'] == True) | (result['is_liquidation'] == True)]
for idx, row in events.iterrows():
    parts = []
    if row['signal'] in ['BUY', 'SELL']:
        parts.append(row['signal'])
    if row['partial_tp']:
        parts.append("TP")
    if row['is_liquidation']:
        parts.append("LIQ")
    event_str = " + ".join(parts)
    print(f"{idx.strftime('%H:%M'):<8} {int(row['pos_debug']):<5} {event_str:<20} {row['Close']:<8.0f} {row['session_pl']:<8.0f}")
