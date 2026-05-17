"""Compare user's 04/21/26 trades vs Fred's algo output."""
import sys, os
sys.path.insert(0, '.')
import pandas as pd, pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
date_str = "2026-04-21"
fpath = os.path.join(DATA_ROOT, f"CBOT_MINI_YM1_{date_str}.csv")

df = pd.read_csv(fpath, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(EST)
day_start = pd.Timestamp(f"{date_str} 09:30", tz=EST)
day_end = pd.Timestamp(f"{date_str} 11:00", tz=EST)
df = df[(df.index >= day_start) & (df.index <= day_end)]

print(f"Bars loaded: {len(df)} (9:30-11:00)")

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

result = run_trading_algo_fast(df, date_str, "09:30", "11:00", config=config)

print("=" * 90)
print(f"FRED vs USER: {date_str} (9:30-11:00)")
print("=" * 90)

# Fred's trades
print("\nFRED'S TRADES:")
print(f"{'Time':<8} {'Pos':<5} {'Signal':<8} {'Close':<8} {'TP':<4} {'LIQ':<4} {'PL':<8}")
print("-" * 55)

events = result[(result['signal'].isin(['BUY', 'SELL'])) | (result['partial_tp'] == True)]
for idx, row in events.iterrows():
    sig = row['signal'] if row['signal'] in ['BUY', 'SELL'] else ""
    tp = "TP" if row['partial_tp'] else ""
    liq = "LIQ" if row.get('is_liquidation', False) else ""
    print(f"{idx.strftime('%H:%M'):<8} {int(row['pos_debug']):<5} {sig:<8} {row['Close']:<8.0f} {tp:<4} {liq:<4} {row['session_pl']:<8.0f}")

print(f"\nFinal P/L: {result.iloc[-1]['session_pl']:.0f} pts")

# User's trades for comparison
print("\n" + "=" * 90)
print("USER'S TRADES (from screenshot):")
print("=" * 90)
print("""
1. BUY  2 @ 49910  (price closed above purple line)
2. SELL 1 @ 49960  (TP of half at 50 points)
3. SELL 1 @ 50013  (LIQ because of 100 point spike)
4. BUY  2 @ 50039  (price closed above steeper purple)
5. SELL 4 @ 50008  (reversed: price closed below blue line)
6. BUY  1 @ 49958  (TP of half at 50 points)
7. BUY  3 @ 50000  (reversed to 2 long: price closed above purple)
8. SELL 4 @ 49963  (reversed: price closed below blue line)
9. BUY  4 @ 49992  (reversed: price closed above purple line)
10.SELL 4 @ 49933  (reversed: price closed below blue line)
11.BUY  1 @ 49913  (accidental TP limit order from 49963 short)
   Then rode short remainder of morning.

User P/L: +$1,005 (+201 pts on $5/pt YM)
User stats: 9 trades, 55.56% win, profit factor 0.74
""")

# Show price action around key times
print("=" * 90)
print("PRICE ACTION AT KEY LEVELS:")
print("=" * 90)
key_prices = [49910, 49960, 50013, 50039, 50008, 49958, 50000, 49963, 49992, 49933]
for price in key_prices:
    bars_at = result[(result['Close'] >= price - 5) & (result['Close'] <= price + 5)]
    if len(bars_at) > 0:
        first = bars_at.index[0]
        print(f"  ~{price}: first seen at {first.strftime('%H:%M')} (Close={result.loc[first, 'Close']:.0f})")
