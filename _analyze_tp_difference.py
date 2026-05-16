"""Analyze WHY TP on High/Low performs worse than TP on Close.
Hypothesis: When close >= 50, the actual close is often much higher than 50,
so booking at close captures more than 50 pts on the TP contract."""
import sys, os, json
sys.path.insert(0, '.')
import pandas as pd, pytz, numpy as np
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
csv_files = sorted([f for f in os.listdir(DATA_ROOT) if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])

# Run with current code (TP on High) and collect TP bar data
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

# Collect data on TP events
tp_on_high_only = []  # cases where High >= 50 but Close < 50
tp_on_both = []       # cases where both High >= 50 and Close >= 50
close_amounts = []    # when close triggers TP, how much above 50 is the close?

count = 0
for fname in csv_files[-200:]:  # last 200 days for speed
    target_date = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
    fpath = os.path.join(DATA_ROOT, fname)
    try:
        df = pd.read_csv(fpath, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(EST)
        if len(df) < 10:
            continue
        day_start = pd.Timestamp(f"{target_date} 09:30", tz=EST)
        day_end = pd.Timestamp(f"{target_date} 16:59", tz=EST)
        day_data = df[(df.index >= day_start) & (df.index <= day_end)]
        if len(day_data) < 15 or day_data["Volume"].sum() < 100:
            continue
        if day_data["High"].max() == day_data["Low"].min():
            continue

        result = run_trading_algo_fast(day_data, target_date, "09:30", "17:00", config=config)
        
        # Find all signal entries and check TP behavior
        signals = result[result['signal'].isin(['BUY', 'SELL'])]
        
        for sig_idx, sig_row in signals.iterrows():
            entry_price = sig_row['Close']  # entry is at close of signal bar
            is_long = sig_row['signal'] == 'BUY'
            
            # Look at subsequent bars until next signal
            after = result[result.index > sig_idx]
            next_sig = after[after['signal'].isin(['BUY', 'SELL'])]
            if len(next_sig) > 0:
                after = after[after.index < next_sig.index[0]]
            
            for bar_idx, bar in after.iterrows():
                if is_long:
                    high_unrealized = bar['High'] - entry_price
                    close_unrealized = bar['Close'] - entry_price
                else:
                    high_unrealized = entry_price - bar['Low']
                    close_unrealized = entry_price - bar['Close']
                
                if high_unrealized >= 50.0:
                    if close_unrealized >= 50.0:
                        tp_on_both.append(close_unrealized)
                        close_amounts.append(close_unrealized)
                    else:
                        tp_on_high_only.append(close_unrealized)
                    break  # only count first TP opportunity per trade
        
        count += 1
    except Exception:
        continue

print(f"Days analyzed: {count}")
print(f"\n{'='*70}")
print(f"PARTIAL TP ANALYSIS (50 pts threshold)")
print(f"{'='*70}")
print(f"\nTotal trades where High reached +50: {len(tp_on_high_only) + len(tp_on_both)}")
print(f"  - High >= 50 AND Close >= 50: {len(tp_on_both)} ({len(tp_on_both)/(len(tp_on_high_only)+len(tp_on_both))*100:.1f}%)")
print(f"  - High >= 50 BUT Close < 50:  {len(tp_on_high_only)} ({len(tp_on_high_only)/(len(tp_on_high_only)+len(tp_on_both))*100:.1f}%)")

if tp_on_both:
    print(f"\nWhen Close also >= 50:")
    print(f"  Mean close unrealized: {np.mean(tp_on_both):.1f} pts")
    print(f"  Median: {np.median(tp_on_both):.1f} pts")
    print(f"  Max: {np.max(tp_on_both):.1f} pts")

if tp_on_high_only:
    print(f"\nWhen High >= 50 but Close < 50 (TP triggers on High but NOT on Close):")
    print(f"  Mean close unrealized: {np.mean(tp_on_high_only):.1f} pts")
    print(f"  Median: {np.median(tp_on_high_only):.1f} pts")
    print(f"  Min (worst reversal): {np.min(tp_on_high_only):.1f} pts")

print(f"\nKEY INSIGHT:")
print(f"  TP on High books exactly 50 pts every time.")
print(f"  TP on Close books {np.mean(tp_on_both):.1f} pts avg when it triggers (because close > 50).")
print(f"  Difference per TP event: {np.mean(tp_on_both) - 50:.1f} pts EXTRA when using Close.")
print(f"  But High catches {len(tp_on_high_only)} extra TP events that Close misses.")
print(f"  Extra from High-only TPs: {len(tp_on_high_only)} events x 50 pts = {len(tp_on_high_only)*50:.0f} pts gained")
print(f"  Lost from Close TPs: {len(tp_on_both)} events x {np.mean(tp_on_both) - 50:.1f} pts = {len(tp_on_both)*(np.mean(tp_on_both)-50):.0f} pts lost")
