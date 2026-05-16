"""Sweep warmup_minutes from 5 to 20 using subprocess batches."""
import subprocess, sys, os, json, time
import numpy as np

DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
csv_files = sorted([f for f in os.listdir(DATA_ROOT) if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])
total = len(csv_files)
BATCH_SIZE = 50

DAY_END_TIMES = ["10:30", "11:00", "12:00", "14:00", "17:00"]
WARMUP_VALUES = [5, 8, 10, 12, 14, 16, 18, 20]

WORKER_SCRIPT = '''
import sys, os, json
sys.path.insert(0, '.')
import pandas as pd, pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
DAY_END_TIMES = ["10:30", "11:00", "12:00", "14:00", "17:00"]

warmup = int(sys.argv[1])
files = json.loads(sys.argv[2])

config = AlgoConfig(
    warmup_minutes=warmup,
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

results = {}
for fname in files:
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
        if len(day_data) < 15:
            continue
        if day_data["Volume"].sum() < 100:
            continue
        if day_data["High"].max() == day_data["Low"].min():
            continue
        day_algo = run_trading_algo_fast(day_data, target_date, "09:30", "17:00", config=config)
        day_results = {}
        for et in DAY_END_TIMES:
            end_ts = pd.Timestamp(f"{target_date} {et}", tz=EST)
            sliced = day_algo[(day_algo.index >= day_start) & (day_algo.index <= end_ts)]
            if len(sliced) < 2:
                continue
            pl = float(sliced["session_pl"].iloc[-1])
            if pl != 0.0:
                day_results[et] = pl
        if day_results:
            results[target_date] = day_results
    except Exception:
        continue

print(json.dumps(results))
'''

print(f"WARMUP SWEEP: {WARMUP_VALUES}")
print(f"Files: {total}, Batch size: {BATCH_SIZE}")
print(f"End times: {DAY_END_TIMES}")
print("=" * 90)

all_results = {}

for warmup in WARMUP_VALUES:
    t0 = time.time()
    totals = {et: {"trades":0,"pl":0.0,"winners":0,"losers":0,"daily_pls":[]} for et in DAY_END_TIMES}
    
    for batch_start in range(0, total, BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, total)
        batch_files = csv_files[batch_start:batch_end]
        try:
            result = subprocess.run(
                [sys.executable, "-c", WORKER_SCRIPT, str(warmup), json.dumps(batch_files)],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0 and result.stdout.strip():
                batch_results = json.loads(result.stdout.strip())
                for date_str, day_pls in batch_results.items():
                    for et, pl in day_pls.items():
                        if et in totals:
                            totals[et]["trades"] += 1
                            totals[et]["pl"] += pl
                            totals[et]["winners"] += 1 if pl > 0 else 0
                            totals[et]["losers"] += 1 if pl <= 0 else 0
                            totals[et]["daily_pls"].append(pl)
        except (subprocess.TimeoutExpired, json.JSONDecodeError):
            pass

    elapsed = time.time() - t0
    all_results[warmup] = totals
    
    # Print row for this warmup value
    t17 = totals["17:00"]
    tr = t17["trades"]; wr = t17["winners"]/tr*100 if tr else 0
    avg = np.mean(t17["daily_pls"]) if t17["daily_pls"] else 0
    print(f"  warmup={warmup:>2}min | 17:00: {tr} days, {wr:.1f}% win, {avg:+.1f} pts/day | {elapsed:.0f}s")

# Final summary table
print(f"\n{'='*90}")
print(f"{'Warmup':<8}", end="")
for et in DAY_END_TIMES:
    print(f"{'|  ' + et + ' avg':>14}", end="")
print()
print("-" * 90)

for warmup in WARMUP_VALUES:
    print(f"{warmup:>4} min", end="")
    for et in DAY_END_TIMES:
        t = all_results[warmup][et]
        avg = np.mean(t["daily_pls"]) if t["daily_pls"] else 0
        print(f"  | {avg:>+7.1f}", end="")
    print()
