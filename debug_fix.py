"""Compare original vs fast on 20 MORE new days (batch 3)."""
import sys, pandas as pd, pytz, os, time as tm
from TradingAlgo import run_trading_algo, AlgoConfig
from TradingAlgoFast import run_trading_algo_fast

est = pytz.timezone("US/Eastern")
data_root = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1130")
files = sorted([f for f in os.listdir(data_root) if f.endswith(".csv")])

already_tested = {
    "2024-01-02","2024-02-12","2024-03-22","2024-05-03","2024-06-13",
    "2024-07-24","2024-09-03","2024-10-14","2024-11-22","2025-01-06",
    "2025-02-14","2025-03-27","2025-05-08","2025-06-18","2025-07-29",
    "2025-09-08","2025-10-17","2025-11-27","2026-01-09","2026-02-19",
    "2024-01-03","2024-02-13","2024-03-25","2024-05-06","2024-06-14",
    "2024-07-25","2024-09-04","2024-10-15","2024-11-25","2025-01-07",
    "2025-02-17","2025-03-28","2025-05-09","2025-06-19","2025-07-30",
    "2025-09-09","2025-10-20","2025-11-28","2026-01-12","2026-02-20",
}

remaining = [f for f in files
             if f.replace("CBOT_MINI_YM1_","").replace(".csv","") not in already_tested]
print(f"Remaining untested files: {len(remaining)}", flush=True)

step = max(1, len(remaining) // 20)
test_files = remaining[2::step][:20]
print(f"Testing {len(test_files)} days\n", flush=True)

config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0, max_loss_per_trade=0)

matches = 0; mismatches = 0; total_orig = 0; total_fast = 0

for fname in test_files:
    target_date = fname.replace("CBOT_MINI_YM1_","").replace(".csv","")
    fpath = os.path.join(data_root, fname)
    df = pd.read_csv(fpath, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)

    t0 = tm.time()
    try:
        orig = run_trading_algo(df, target_date, "09:30", "10:30", config=config)
    except Exception as e:
        print(f"  {target_date}: ORIG ERROR - {e}", flush=True); continue
    t1 = tm.time()
    try:
        fast = run_trading_algo_fast(df, target_date, "09:30", "10:30", config=config)
    except Exception as e:
        print(f"  {target_date}: FAST ERROR - {e}", flush=True); continue
    t2 = tm.time()
    total_orig += t1-t0; total_fast += t2-t1

    orig_sigs = [(ts.strftime("%H:%M"), row["signal"]) for ts, row in orig.iterrows() if row.get("signal") in ("BUY","SELL")]
    fast_sigs = [(ts.strftime("%H:%M"), row["signal"]) for ts, row in fast.iterrows() if row.get("signal") in ("BUY","SELL")]

    if orig_sigs == fast_sigs:
        matches += 1
        print(f"  {target_date}: MATCH ({len(orig_sigs)} signals)", flush=True)
    else:
        mismatches += 1
        print(f"  {target_date}: MISMATCH orig={len(orig_sigs)} fast={len(fast_sigs)}", flush=True)
        for s in orig_sigs:
            if s not in fast_sigs: print(f"    MISSING in fast: {s}", flush=True)
        for s in fast_sigs:
            if s not in orig_sigs: print(f"    EXTRA in fast: {s}", flush=True)

print(f"\n{matches} match, {mismatches} mismatch out of {matches+mismatches} days", flush=True)
if total_fast > 0:
    print(f"Total time: orig={total_orig:.1f}s  fast={total_fast:.1f}s  speedup={total_orig/total_fast:.1f}x", flush=True)
print(f"\nCumulative: 60 unique days tested across 3 batches", flush=True)
