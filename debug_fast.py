"""Compare original vs fast on 20 different days spread across the dataset."""
import pandas as pd, pytz, os, time as tm
from TradingAlgo import run_trading_algo, AlgoConfig
from TradingAlgoFast import run_trading_algo_fast

est = pytz.timezone("US/Eastern")
data_root = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1130")
files = sorted([f for f in os.listdir(data_root) if f.endswith(".csv")])

# Pick 20 days spread evenly across the dataset
step = max(1, len(files) // 20)
test_files = files[::step][:20]

config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0, max_loss_per_trade=0)

matches = 0; mismatches = 0; total_orig = 0; total_fast = 0

for fname in test_files:
    target_date = fname.replace("CBOT_MINI_YM1_","").replace(".csv","")
    df = pd.read_csv(os.path.join(data_root, fname), index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)

    t0 = tm.time()
    try: orig = run_trading_algo(df, target_date, "09:30", "10:30", config=config)
    except: continue
    t1 = tm.time()
    try: fast = run_trading_algo_fast(df, target_date, "09:30", "10:30", config=config)
    except: continue
    t2 = tm.time()
    total_orig += t1-t0; total_fast += t2-t1

    orig_sigs = [(ts.strftime("%H:%M"), row["signal"]) for ts, row in orig.iterrows() if row.get("signal") in ("BUY","SELL")]
    fast_sigs = [(ts.strftime("%H:%M"), row["signal"]) for ts, row in fast.iterrows() if row.get("signal") in ("BUY","SELL")]

    if orig_sigs == fast_sigs:
        matches += 1
        print(f"  {target_date}: MATCH ({len(orig_sigs)} signals)")
    else:
        mismatches += 1
        print(f"  {target_date}: MISMATCH orig={len(orig_sigs)} fast={len(fast_sigs)}")
        for s in orig_sigs:
            if s not in fast_sigs: print(f"    MISSING in fast: {s}")
        for s in fast_sigs:
            if s not in orig_sigs: print(f"    EXTRA in fast: {s}")

print(f"\n{matches} match, {mismatches} mismatch out of {matches+mismatches} days")
print(f"Total time: orig={total_orig:.1f}s  fast={total_fast:.1f}s  speedup={total_orig/total_fast:.1f}x")
