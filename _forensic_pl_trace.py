"""FORENSIC: Trace P/L calculation for trades 12:26 onwards on May 14."""
import sys, os
sys.path.insert(0, '.')
import pandas as pd, pytz
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
print("P/L VERIFICATION: Trades from 12:26 onwards")
print("=" * 90)
print()
print("Legend: pos_debug values: 0=flat, 1=long, 2=short")
print("       num_contracts=2, partial_tp_pts=50")
print()

# Manual P/L trace
# Starting state at 12:26: PL=346
# Need to trace each trade's contribution

events = result[(result['signal'].isin(['BUY', 'SELL'])) | (result['partial_tp'] == True)]
events_from_1226 = events[events.index >= pd.Timestamp("2026-05-14 12:24", tz=EST)]

print(f"{'Time':<8} {'Pos':<5} {'Event':<15} {'Close':<8} {'PL':<8} {'Calculation'}")
print("-" * 100)

prev_entry = None
prev_pos = None
prev_pl = None
prev_partial = False

for idx, row in events_from_1226.iterrows():
    parts = []
    if row['signal'] in ['BUY', 'SELL']:
        parts.append(row['signal'])
    if row['partial_tp']:
        parts.append("TP")
    if row['is_liquidation']:
        parts.append("LIQ")
    event_str = " + ".join(parts)
    
    # Calculate what the P/L change should be
    calc = ""
    pos = int(row['pos_debug'])
    pl = row['session_pl']
    close = row['Close']
    
    if prev_pl is not None:
        delta = pl - prev_pl
        calc = f"delta={delta:+.0f}"
    
    print(f"{idx.strftime('%H:%M'):<8} {pos:<5} {event_str:<15} {close:<8.0f} {pl:<8.0f} {calc}")
    
    prev_pl = pl

# Now manually verify each transition
print()
print("=" * 90)
print("MANUAL P/L VERIFICATION")
print("=" * 90)

print("""
12:24  SELL @ 50215 | pos=2 (short) | PL=240
  - Previous was long from 11:52 BUY @ 50234
  - Exit long: (50215 - 50234) * contracts_remaining
  - If partial_taken=True: (50215-50234)*1 = -19
  - If partial_taken=False: (50215-50234)*2 = -38
  - PL went from 278 to 240 = delta -38 → partial_taken was FALSE (2 contracts)
  - Wait: 11:51 had TP+LIQ, went flat. 11:52 BUY opened new position. partial_taken=False.
  - (50215-50234)*2 = -38. 278 + (-38) = 240. CORRECT.

12:26  BUY + TP + LIQ @ 50162 | pos=0 (flat) | PL=346
  - Was short from 12:24 SELL @ 50215
  - TP fires: unrealized = (50215-50162) = 53 >= 50. Books 53 on 1 contract. partial_taken=True.
  - Spike profit fires: unrealized = 53 >= 50, within 9 bars (bar 2 of entry). 
    contracts_remaining = 1 (partial_taken=True). Books 53*1 = 53.
  - Total booked: 53 (TP) + 53 (spike) = 106
  - PL: 240 + 106 = 346. CORRECT.
  - BUT: We booked the SAME 53 pts TWICE! Once as TP, once as spike exit.
  - This is DOUBLE-COUNTING.

12:33  SELL @ 50149 | pos=2 (short) | PL=346
  - Was flat (pos=0 after 12:26 LIQ). New short entry. No P/L change.
  - PL stays 346. CORRECT (new entry, no exit to book).

12:54  TP @ 50099 | pos=2 (short) | PL=446
  - Short from 12:33 @ 50149. 
  - unrealized = (50149-50099) = 50 >= 50. Books 50 on 1 contract.
  - PL: 346 + 50 = 396... but actual is 446.
  - WAIT. Let me check: 446 - 346 = 100. That's 50 pts * 2 contracts?
  - No, TP should only book 1 contract. 
  - Unless session_pl_arr includes unrealized on remaining contract.
  - session_pl_arr[i] = session_pl + (entry_price - close) for short
  - session_pl after TP = 346 + 50 = 396
  - unrealized on remaining 1 contract = (50149 - 50099) = 50
  - session_pl_arr = 396 + 50 = 446. CORRECT (realized + unrealized display).

13:46  BUY @ 50169 | pos=1 (long) | PL=376
  - Was short from 12:33 @ 50149, partial_taken=True (TP fired at 12:54)
  - Exit short: (50149 - 50169) * 1 = -20 (1 contract remaining)
  - realized session_pl = 396 + (-20) = 376
  - New long entry @ 50169. PL=376. CORRECT.

14:01  SELL @ 50075 | pos=2 (short) | PL=188
  - Was long from 13:46 @ 50169, partial_taken=False
  - Exit long: (50075 - 50169) * 2 = -188
  - realized session_pl = 376 + (-188) = 188. CORRECT.

14:14  BUY @ 50159 | pos=1 (long) | PL=20
  - Was short from 14:01 @ 50075, partial_taken=False
  - Exit short: (50075 - 50159) * 2 = -168
  - realized session_pl = 188 + (-168) = 20. CORRECT.

16:16  SELL @ 50132 | pos=2 (short) | PL=-34
  - Was long from 14:14 @ 50159, partial_taken=False
  - Exit long: (50132 - 50159) * 2 = -54
  - realized session_pl = 20 + (-54) = -34. CORRECT.
""")

print("=" * 90)
print("FINDINGS")
print("=" * 90)
print("""
1. P/L calculations are CORRECT for individual trades.

2. DOUBLE-COUNTING at 12:26: TP books 53 pts on 1 contract, then spike profit 
   ALSO books 53 pts on the remaining 1 contract. Net: 106 pts booked.
   This is NOT double-counting — it's TP on contract 1 + exit on contract 2.
   Both at the same price. Effectively a full exit at +53 on both contracts.

3. THE REAL PROBLEM: After 12:54 TP, the system has 446 pts of profit.
   Then it gives back 480 pts in the last 3 trades:
   - 13:46 BUY: -20 (reversal from profitable short)
   - 14:01 SELL: -188 (2 contracts, 94 pts against)
   - 14:14 BUY: -168 (2 contracts, 84 pts against)  
   - 16:16 SELL: -54 (2 contracts, 27 pts against)
   Total giveback: -430 pts (from 446 to -34 final... wait that's -480)
   
   Actually: 446 → 376 (-70 unrealized swing) → 188 → 20 → -34
   From peak 446 to final -34 = gave back 480 pts.

4. The afternoon trades (13:46-16:16) are ALL losers, each losing 
   on 2 full contracts because partial_taken resets to False on each new entry.
   No TP fires on any of these because they never reach +50.

5. KEY INSIGHT: The system makes money in the morning trend (9:43-12:54)
   then gives it ALL back in afternoon chop (13:46-16:16) where it 
   whipsaws on 2 contracts each time.
""")
