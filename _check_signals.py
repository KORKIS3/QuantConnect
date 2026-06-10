import pandas as pd

df = pd.read_csv(r'C:\Users\Administrator\Desktop\IB_Live\tracking\YM_tracking_2026-06-09_0930.csv')
df['time'] = pd.to_datetime(df['time'])
after = df[df['time'] >= '2026-06-09 12:30:00']

# Algo signals after 12:30
algo_signals = after[after['signal'].isin(['BUY','SELL'])][['time','signal','buy_price','sell_price','Close','session_pl']].copy()
print('=== ALGO SIGNALS (from CSV) after 12:30 ===')
for _, row in algo_signals.iterrows():
    price = row['buy_price'] if row['signal'] == 'BUY' else row['sell_price']
    print(f"  {row['time'].strftime('%H:%M')}  {row['signal']:4s}  @ {price:.0f}  session_pl={row['session_pl']:.1f}")
print(f"  Total algo signals: {len(algo_signals)}")
print()

# IB signals after 12:30
ib_signals = after[after['ib_signal'].isin(['BUY','SELL'])][['time','ib_signal','ib_buy_price','ib_sell_price','Close','ib_session_pl','ib_realized_pl','ib_unrealized_pl']].copy()
print('=== IB SIGNALS (actual fills) after 12:30 ===')
for _, row in ib_signals.iterrows():
    price = row['ib_buy_price'] if row['ib_signal'] == 'BUY' else row['ib_sell_price']
    print(f"  {row['time'].strftime('%H:%M')}  {row['ib_signal']:4s}  @ {price:.0f}  ib_session_pl={row['ib_session_pl']:.1f}  realized={row['ib_realized_pl']:.1f}")
print(f"  Total IB signals: {len(ib_signals)}")
print()

# Current state
last = after.iloc[-1]
print(f"=== CURRENT STATE (last bar: {last['time'].strftime('%H:%M')}) ===")
print(f"  Algo session_pl: {last['session_pl']:.1f}")
print(f"  IB session_pl:   {last['ib_session_pl']:.1f}")
print(f"  IB position:     {last['ib_position']}")
print(f"  IB realized:     {last['ib_realized_pl']:.1f}")
print(f"  IB unrealized:   {last['ib_unrealized_pl']:.1f}")
print()

# Also show full day signals for context
print('=== ALGO SIGNALS (FULL DAY) ===')
all_algo = df[df['signal'].isin(['BUY','SELL'])][['time','signal','buy_price','sell_price','Close','session_pl']].copy()
for _, row in all_algo.iterrows():
    price = row['buy_price'] if row['signal'] == 'BUY' else row['sell_price']
    print(f"  {row['time'].strftime('%H:%M')}  {row['signal']:4s}  @ {price:.0f}  session_pl={row['session_pl']:.1f}")
print()

print('=== IB SIGNALS (FULL DAY) ===')
all_ib = df[df['ib_signal'].isin(['BUY','SELL'])][['time','ib_signal','ib_buy_price','ib_sell_price','Close','ib_session_pl','ib_realized_pl','ib_unrealized_pl']].copy()
for _, row in all_ib.iterrows():
    price = row['ib_buy_price'] if row['ib_signal'] == 'BUY' else row['ib_sell_price']
    print(f"  {row['time'].strftime('%H:%M')}  {row['ib_signal']:4s}  @ {price:.0f}  ib_session_pl={row['ib_session_pl']:.1f}  realized={row['ib_realized_pl']:.1f}")
