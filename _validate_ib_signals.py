"""Validate that IB order logic matches CSV algo signals for today"""
import pandas as pd
import pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

# Load today's data (May 12, 2026)
fpath = r"C:\Users\Administrator\Desktop\2YearsData\full_day\CBOT_MINI_YM1_2026-05-12.csv"
df = pd.read_csv(fpath, index_col=0, parse_dates=True)
est = pytz.timezone("US/Eastern")
df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)

# Filter to day session
day_start = pd.Timestamp("2026-05-12 09:30", tz=est)
day_end = pd.Timestamp("2026-05-12 17:00", tz=est)
df = df[(df.index >= day_start) & (df.index <= day_end)]

# Config matching live trading
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
    steep_line_proximity=5.0,
    steep_line_exit_only=False,
)

# Run algo
result = run_trading_algo_fast(df, target_date="2026-05-12", start_time="09:30", end_time="17:00", config=config)

# Extract signals
signals = result[result['signal'].isin(['BUY', 'SELL'])].copy()

print("\n" + "="*80)
print("ALGO SIGNALS FROM CSV DATA")
print("="*80)
print(f"Total signals: {len(signals)}")
print(f"BUY signals: {(signals['signal'] == 'BUY').sum()}")
print(f"SELL signals: {(signals['signal'] == 'SELL').sum()}")
print("\nSignal details:")
print(signals[['signal', 'buy_price', 'sell_price', 'position', 'pl', 'session_pl']].to_string())

print("\n" + "="*80)
print("WHAT IB WOULD RECEIVE")
print("="*80)

# Simulate IB order logic (from InteractiveBrokers.py)
# IB tracks actual contract count: positive=long, negative=short, zero=flat
ib_position = 0  # number of contracts (positive=long, negative=short)
ib_orders = []

for idx, row in signals.iterrows():
    signal = row['signal']
    price = row['buy_price'] if signal == 'BUY' else row['sell_price']
    time_str = idx.strftime('%H:%M')
    
    # IB duplicate protection: check position, not previous signal
    skip = False
    if signal == 'BUY' and ib_position > 0:
        print(f"SKIPPED duplicate BUY at {time_str} (already long, ib_pos={ib_position})")
        skip = True
    elif signal == 'SELL' and ib_position < 0:
        print(f"SKIPPED duplicate SELL at {time_str} (already short, ib_pos={ib_position})")
        skip = True
    
    if not skip:
        ib_orders.append({
            'time': idx,
            'signal': signal,
            'price': price,
            'contracts': 2
        })
        # Update IB position (2 contracts per order)
        prev_pos = ib_position
        if signal == 'BUY':
            ib_position += 2  # buy 2 contracts
        elif signal == 'SELL':
            ib_position -= 2  # sell 2 contracts
        
        # Debug: show all position changes
        print(f"  {time_str} {signal}: pos {prev_pos} -> {ib_position}")

print(f"\nTotal IB orders: {len(ib_orders)}")
print(f"BUY orders: {sum(1 for o in ib_orders if o['signal'] == 'BUY')}")
print(f"SELL orders: {sum(1 for o in ib_orders if o['signal'] == 'SELL')}")

print("\nIB order sequence:")
for order in ib_orders:
    print(f"{order['time'].strftime('%H:%M')} - {order['signal']} {order['contracts']} @ {order['price']:.0f}")

print("\n" + "="*80)
print("VALIDATION")
print("="*80)

# Check for discrepancies
algo_buys = (signals['signal'] == 'BUY').sum()
algo_sells = (signals['signal'] == 'SELL').sum()
ib_buys = sum(1 for o in ib_orders if o['signal'] == 'BUY')
ib_sells = sum(1 for o in ib_orders if o['signal'] == 'SELL')

if algo_buys == ib_buys and algo_sells == ib_sells:
    print("✓ PASS: IB orders match algo signals")
    print(f"  {ib_buys} BUY orders, {ib_sells} SELL orders")
else:
    print("✗ FAIL: Mismatch detected!")
    print(f"  Algo: {algo_buys}B {algo_sells}S")
    print(f"  IB:   {ib_buys}B {ib_sells}S")
    print(f"  Difference: {algo_buys - ib_buys}B {algo_sells - ib_sells}S")

print("="*80)
