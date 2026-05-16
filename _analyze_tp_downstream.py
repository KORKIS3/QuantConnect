"""Analyze downstream effect: after TP triggers on High, what happens to remaining contract?
The theory: TP on High fires earlier, so the remaining 1 contract rides less of the move.
With TP on Close, you stay at 2 contracts longer, capturing more on both."""
import sys, os
sys.path.insert(0, '.')
import pandas as pd, pytz, numpy as np
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
csv_files = sorted([f for f in os.listdir(DATA_ROOT) if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])

config = AlgoConfig(
    warmup_minutes=8,
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

# Compare: on days where High triggers TP but Close doesn't on same bar,
# what is the FINAL P/L of that trade (when position eventually exits)?
# This tells us if taking TP early costs us on the remaining contract.

early_tp_final_pls = []  # P/L of trades where High triggered TP (bar where High>=50 but Close<50)
no_tp_final_pls = []     # P/L of same trades if we DIDN'T take TP (2 contracts to exit)

count = 0
for fname in csv_files[-100:]:
    target_date = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
    fpath = os.path.join(DATA_ROOT, fname)
    try:
        df = pd.read_csv(fpath, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(EST)
        day_start = pd.Timestamp(f"{target_date} 09:30", tz=EST)
        day_end = pd.Timestamp(f"{target_date} 16:59", tz=EST)
        day_data = df[(df.index >= day_start) & (df.index <= day_end)]
        if len(day_data) < 15 or day_data["Volume"].sum() < 100:
            continue
        if day_data["High"].max() == day_data["Low"].min():
            continue

        result = run_trading_algo_fast(day_data, target_date, "09:30", "17:00", config=config)
        
        # Check: does partial_tp column exist and fire?
        tp_bars = result[result['partial_tp'] == True]
        signals = result[result['signal'].isin(['BUY', 'SELL'])]
        
        for i, (sig_idx, sig_row) in enumerate(signals.iterrows()):
            entry_price = sig_row['Close']
            is_long = sig_row['signal'] == 'BUY'
            
            # Find exit (next signal or end of day)
            remaining_sigs = signals[signals.index > sig_idx]
            if len(remaining_sigs) > 0:
                exit_idx = remaining_sigs.index[0]
                exit_price = result.loc[exit_idx, 'Close']
            else:
                exit_price = result.iloc[-1]['Close']
            
            # Did TP fire on this trade?
            trade_tps = tp_bars[(tp_bars.index > sig_idx) & (tp_bars.index <= exit_idx if len(remaining_sigs) > 0 else tp_bars.index <= result.index[-1])]
            
            if len(trade_tps) > 0:
                # TP fired. Calculate:
                # With TP: 50 pts (1 contract) + (exit - entry) on remaining 1 contract
                # Without TP: (exit - entry) * 2 contracts
                if is_long:
                    exit_unrealized = exit_price - entry_price
                else:
                    exit_unrealized = entry_price - exit_price
                
                with_tp = 50.0 + exit_unrealized  # 1 contract TP + 1 contract ride
                without_tp = exit_unrealized * 2   # 2 contracts ride to exit
                
                early_tp_final_pls.append(with_tp)
                no_tp_final_pls.append(without_tp)
        
        count += 1
    except Exception:
        continue

print(f"Days analyzed: {count}")
print(f"Trades with TP triggered: {len(early_tp_final_pls)}")
print(f"\n{'='*70}")
print(f"WITH TP (50 pts on 1 contract + ride remaining):")
print(f"  Mean P/L per trade: {np.mean(early_tp_final_pls):.1f} pts")
print(f"  Total: {np.sum(early_tp_final_pls):.0f} pts")
print(f"\nWITHOUT TP (2 contracts ride to exit):")
print(f"  Mean P/L per trade: {np.mean(no_tp_final_pls):.1f} pts")
print(f"  Total: {np.sum(no_tp_final_pls):.0f} pts")
print(f"\nDifference (TP - no TP): {np.sum(early_tp_final_pls) - np.sum(no_tp_final_pls):.0f} pts")
print(f"Per trade: {np.mean(early_tp_final_pls) - np.mean(no_tp_final_pls):.1f} pts")

# Breakdown: trades where exit was profitable vs unprofitable
profitable_exits = [i for i, x in enumerate(no_tp_final_pls) if x > 0]
losing_exits = [i for i, x in enumerate(no_tp_final_pls) if x <= 0]
print(f"\nOn WINNING trades (exit > entry):")
print(f"  Count: {len(profitable_exits)}")
if profitable_exits:
    print(f"  With TP avg: {np.mean([early_tp_final_pls[i] for i in profitable_exits]):.1f}")
    print(f"  Without TP avg: {np.mean([no_tp_final_pls[i] for i in profitable_exits]):.1f}")
print(f"\nOn LOSING trades (exit < entry):")
print(f"  Count: {len(losing_exits)}")
if losing_exits:
    print(f"  With TP avg: {np.mean([early_tp_final_pls[i] for i in losing_exits]):.1f}")
    print(f"  Without TP avg: {np.mean([no_tp_final_pls[i] for i in losing_exits]):.1f}")
