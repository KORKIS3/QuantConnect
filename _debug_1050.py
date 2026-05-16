"""Debug the 10:50 TP+LIQ issue"""
import pandas as pd
import pytz

_EST = pytz.timezone("US/Eastern")

# Load tracking data
df = pd.read_csv("~/Desktop/IB_Live/tracking/YM_tracking_DUO158495_2026-05-14_0930.csv", 
                 index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)

# Find all signals
signals = df[df['signal'].notna()].copy()
print("ALL SIGNALS:")
print(signals[['Close', 'signal', 'buy_price', 'sell_price', 'partial_tp', 
               'session_pl', 'position', 'is_liquidation']].to_string())

print("\n" + "="*80)
print("ENTRY FOR THE LONG THAT EXITED AT 10:50:")
print("="*80)

# Find the BUY before 10:50
buys_before_1050 = signals[(signals['signal'] == 'BUY') & (signals.index < '2026-05-14 10:50')]
if len(buys_before_1050) > 0:
    last_buy = buys_before_1050.iloc[-1]
    entry_price = last_buy['buy_price']
    entry_time = last_buy.name
    print(f"Entry time: {entry_time}")
    print(f"Entry price: {entry_price}")
    
    # Check 10:50 bar
    bar_1050 = df.loc['2026-05-14 10:50']
    close_1050 = bar_1050['Close']
    unrealized = close_1050 - entry_price
    
    print(f"\n10:50 bar:")
    print(f"  Close: {close_1050}")
    print(f"  Unrealized P/L: {unrealized:.1f} pts")
    print(f"  Partial TP threshold: 50 pts")
    print(f"  Partial TP triggered: {bar_1050['partial_tp']}")
    print(f"  Blue ray: {bar_1050['blue_ray']:.2f}")
    print(f"  Distance from blue ray: {close_1050 - bar_1050['blue_ray']:.1f} pts")
    
    # Check steep blue lines
    for i in range(4):
        col = f'blue_steep_{i}_vals'
        if col in df.columns:
            val = bar_1050[col]
            if pd.notna(val):
                print(f"  Blue steep {i}: {val:.2f} (distance: {close_1050 - val:.1f} pts)")
