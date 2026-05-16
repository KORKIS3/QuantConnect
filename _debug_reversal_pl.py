"""Debug the reversal P/L calculation on May 8"""
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

# Focus on trades 5 and 6
trades = result[result['signal'].isin(['BUY', 'SELL'])].copy()

print("Trade 5 and 6 Analysis")
print("="*80)

# Get trades 4, 5, 6 (indices 3, 4, 5)
for i, (idx, row) in enumerate(trades.iloc[3:7].iterrows()):
    time_str = idx.strftime('%H:%M')
    signal_price = row['buy_price'] if row['signal'] == 'BUY' else row['sell_price']
    
    print(f"\nTrade {i+4}: {time_str} {row['signal']} @ {signal_price:.0f}")
    print(f"  Position after: {row['position']}")
    print(f"  Session P/L: {row['session_pl']:.1f}")
    print(f"  Partial TP: {row['partial_tp']}")
    
    # Manual calculation
    if i == 0:  # Trade 4 (BUY @ 49722)
        print(f"  Expected: Close short from 49708, entry was 49722")
        print(f"  P/L from closing short: 49722 - 49722 = 0")
        print(f"  Previous session_pl: -86")
        print(f"  New session_pl should be: -86 + 0 = -86 ✓")
    
    elif i == 1:  # Trade 5 (SELL @ 49708)
        print(f"  Expected: Close long from 49722, entry was 49722")
        print(f"  P/L from closing long: 49708 - 49722 = -14")
        print(f"  Previous session_pl: -86")
        print(f"  New session_pl should be: -86 + (-14) = -100 ✓")
    
    elif i == 2:  # Trade 6 (BUY @ 49701)
        print(f"  Expected: Close short from 49708, entry was 49708")
        print(f"  P/L from closing short: 49708 - 49701 = +7")
        print(f"  Previous session_pl: -100")
        print(f"  New session_pl should be: -100 + 7 = -93")
        print(f"  ACTUAL session_pl: -66")
        print(f"  ERROR: {-66 - (-93)} = +27 points")

# Check what's in the result at those exact bars
print("\n" + "="*80)
print("Checking bars around trade 6 (15:45)")
print("="*80)

trade6_time = pd.Timestamp("2026-05-08 15:45", tz=est)
window = result[(result.index >= trade6_time - pd.Timedelta(minutes=2)) & 
                (result.index <= trade6_time + pd.Timedelta(minutes=2))].copy()

for idx, row in window.iterrows():
    time_str = idx.strftime('%H:%M')
    print(f"\n{time_str}:")
    print(f"  Close: {row['Close']:.0f}")
    print(f"  Position: {row['position']}")
    print(f"  Signal: {row['signal']}")
    print(f"  Session P/L: {row['session_pl']:.1f}")
    print(f"  Partial TP: {row['partial_tp']}")
