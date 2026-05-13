"""Debug script to trace EXACTLY what triggers SELL signals at 09:42 and 09:46"""
import pandas as pd
import numpy as np
import pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

# Load May 12 data
fpath = r"C:\Users\Administrator\Desktop\2YearsData\full_day\CBOT_MINI_YM1_2026-05-12.csv"
df = pd.read_csv(fpath, index_col=0, parse_dates=True)
est = pytz.timezone("US/Eastern")
df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)

# Filter to day session
day_start = pd.Timestamp("2026-05-12 09:30", tz=est)
day_end = pd.Timestamp("2026-05-12 17:00", tz=est)
df = df[(df.index >= day_start) & (df.index <= day_end)]

# Config from commit 8a15b10
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
    steep_line_exit_only=False,
)

# Run algo
result = run_trading_algo_fast(
    df, 
    target_date="2026-05-12",
    start_time="09:30",
    end_time="17:00",
    config=config
)

# Focus on 09:40-09:50
start = pd.Timestamp("2026-05-12 09:40", tz=est)
end = pd.Timestamp("2026-05-12 09:50", tz=est)
window = result[(result.index >= start) & (result.index <= end)].copy()

print("\n" + "="*120)
print("SIGNAL ANALYSIS: 09:40 - 09:50")
print("="*120)

for idx, row in window.iterrows():
    time_str = idx.strftime("%H:%M")
    close = row['Close']
    signal = row['signal']
    pos = row['position']
    pl = row['pl']
    pos_debug_val = row.get('pos_debug', -1)
    is_liq = row.get('is_liquidation', False)
    partial = row.get('partial_tp', False)
    buy_price = row.get('buy_price', np.nan)
    sell_price = row.get('sell_price', np.nan)
    
    # Check line values
    purple = row['purple_ray']
    blue = row['blue_ray']
    yellow = row['yellow_ray']
    
    # Check steep lines
    blue_steep_0 = row.get('blue_steep_0_vals', np.nan)
    blue_steep_1 = row.get('blue_steep_1_vals', np.nan)
    blue_steep_2 = row.get('blue_steep_2_vals', np.nan)
    purple_steep_0 = row.get('purple_steep_0_vals', np.nan)
    
    # Get previous bar values for cross detection
    prev_idx = window.index.get_loc(idx)
    if prev_idx > 0:
        prev_row = window.iloc[prev_idx - 1]
        prev_close = prev_row['Close']
        prev_purple = prev_row['purple_ray']
        prev_blue = prev_row['blue_ray']
        prev_yellow = prev_row['yellow_ray']
        prev_blue_steep_0 = prev_row.get('blue_steep_0_vals', np.nan)
        prev_blue_steep_1 = prev_row.get('blue_steep_1_vals', np.nan)
        prev_blue_steep_2 = prev_row.get('blue_steep_2_vals', np.nan)
        
        # Detect crosses
        purple_cross = not np.isnan(prev_purple) and not np.isnan(purple) and prev_close >= prev_purple and close < purple
        blue_cross = not np.isnan(prev_blue) and not np.isnan(blue) and prev_close >= prev_blue and close < blue
        yellow_cross = not np.isnan(prev_yellow) and not np.isnan(yellow) and prev_close >= prev_yellow and close < yellow
        blue_steep_0_cross = not np.isnan(prev_blue_steep_0) and not np.isnan(blue_steep_0) and prev_close >= prev_blue_steep_0 and close < blue_steep_0
        blue_steep_1_cross = not np.isnan(prev_blue_steep_1) and not np.isnan(blue_steep_1) and prev_close >= prev_blue_steep_1 and close < blue_steep_1
        blue_steep_2_cross = not np.isnan(prev_blue_steep_2) and not np.isnan(blue_steep_2) and prev_close >= prev_blue_steep_2 and close < blue_steep_2
    else:
        purple_cross = blue_cross = yellow_cross = blue_steep_0_cross = blue_steep_1_cross = blue_steep_2_cross = False
        prev_close = np.nan
    
    # Print bar info
    buy_str = f", Buy={buy_price:.0f}" if pd.notna(buy_price) else ""
    sell_str = f", Sell={sell_price:.0f}" if pd.notna(sell_price) else ""
    print(f"\n{time_str}: Close={close:.0f}, Signal={signal}, Pos={pos}, PosDebug={pos_debug_val}, P/L={pl:.0f}, Liq={is_liq}, Partial={partial}{buy_str}{sell_str}")
    print(f"  Purple={purple:.0f}, Blue={blue:.0f}, Yellow={yellow:.0f}")
    
    if not np.isnan(blue_steep_0):
        print(f"  BlueSteep0={blue_steep_0:.0f}")
    if not np.isnan(blue_steep_1):
        print(f"  BlueSteep1={blue_steep_1:.0f}")
    if not np.isnan(blue_steep_2):
        print(f"  BlueSteep2={blue_steep_2:.0f}")
    
    # Show crosses
    crosses = []
    if purple_cross:
        crosses.append(f"PURPLE CROSS (prev={prev_close:.0f} >= {prev_purple:.0f}, now={close:.0f} < {purple:.0f})")
    if blue_cross:
        crosses.append(f"BLUE CROSS (prev={prev_close:.0f} >= {prev_blue:.0f}, now={close:.0f} < {blue:.0f})")
    if yellow_cross:
        crosses.append(f"YELLOW CROSS (prev={prev_close:.0f} >= {prev_yellow:.0f}, now={close:.0f} < {yellow:.0f})")
    if blue_steep_0_cross:
        crosses.append(f"BLUE STEEP 0 CROSS (prev={prev_close:.0f} >= {prev_blue_steep_0:.0f}, now={close:.0f} < {blue_steep_0:.0f})")
    if blue_steep_1_cross:
        crosses.append(f"BLUE STEEP 1 CROSS (prev={prev_close:.0f} >= {prev_blue_steep_1:.0f}, now={close:.0f} < {blue_steep_1:.0f})")
    if blue_steep_2_cross:
        crosses.append(f"BLUE STEEP 2 CROSS (prev={prev_close:.0f} >= {prev_blue_steep_2:.0f}, now={close:.0f} < {blue_steep_2:.0f})")
    
    if crosses:
        for cross in crosses:
            print(f"  >>> {cross}")
    
    # Highlight signal bars
    if signal != 'flat':
        print(f"  *** SIGNAL: {signal} ***")

print("\n" + "="*120)
print("\nSUMMARY:")
print("="*120)
signals_only = window[window['signal'] != 'flat']
if not signals_only.empty:
    for idx, row in signals_only.iterrows():
        time_str = idx.strftime("%H:%M")
        print(f"{time_str}: {row['signal']} at {row['Close']:.0f}, pos={row['position']}, pl={row['pl']:.0f}")
else:
    print("No signals in this window")
print("="*120)
