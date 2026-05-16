"""Check if steep line cross is happening at 15:45"""
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

# Check 15:44-15:46
trade6_time = pd.Timestamp("2026-05-08 15:45", tz=est)
window = result[(result.index >= trade6_time - pd.Timedelta(minutes=1)) & 
                (result.index <= trade6_time + pd.Timedelta(minutes=1))].copy()

print("Steep line values around 15:45")
print("="*80)

for idx, row in window.iterrows():
    time_str = idx.strftime('%H:%M')
    print(f"\n{time_str}:")
    print(f"  Close: {row['Close']:.0f}")
    print(f"  Position: {row['position']}")
    print(f"  Signal: {row['signal']}")
    
    # Check all steep lines
    for i in range(4):
        blue_steep = row[f'blue_steep_{i}_vals']
        purple_steep = row[f'purple_steep_{i}_vals']
        
        if not pd.isna(blue_steep):
            print(f"  Blue steep {i}: {blue_steep:.1f}")
        if not pd.isna(purple_steep):
            print(f"  Purple steep {i}: {purple_steep:.1f}")
    
    # Check if close crossed any steep lines
    if time_str == '15:45':
        prev_row = result.iloc[result.index.get_loc(idx) - 1]
        prev_close = prev_row['Close']
        
        print(f"\n  Previous close: {prev_close:.0f}")
        print(f"  Current close: {row['Close']:.0f}")
        
        for i in range(4):
            blue_steep_prev = prev_row[f'blue_steep_{i}_vals']
            blue_steep_curr = row[f'blue_steep_{i}_vals']
            
            if not pd.isna(blue_steep_prev) and not pd.isna(blue_steep_curr):
                if prev_close >= blue_steep_prev and row['Close'] < blue_steep_prev:
                    print(f"  ⚠ CROSSED BELOW blue steep {i}! ({blue_steep_prev:.1f})")
