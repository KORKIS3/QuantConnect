"""Run full backtest with partial TP disabled (partial_tp_pts=0)."""
import subprocess, sys, os, json, time
import numpy as np

DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
csv_files = sorted([f for f in os.listdir(DATA_ROOT) if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])
total = len(csv_files)
BATCH_SIZE = 50

DAY_END_TIMES = ["10:00","10:30","11:00","11:30","12:00","13:00","14:00","15:00","16:00","17:00"]
totals = {et: {"trades":0,"pl":0.0,"winners":0,"losers":0,"daily_pls":[]} for et in DAY_END_TIMES}

t_start = time.time()
processed = 0

WORKER_SCRIPT = '''
import sys, os, json
sys.path.insert(0, '.')
import pandas as pd, pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
DAY_END_TIMES = ["10:00","10:30","11:00","11:30","12:00","13:00","14:00","15:00","16:00","17:00"]

config = AlgoConfig(
    warmup_minutes=8,
    steep_angle_threshold=65.0,
    proximity_points=8.0,
    min_reversal_minutes=0,
    min_entry_angle=15.0,
    partial_tp_pts=0.0,
    spike_profit_pts=50.0,
    spike_profit_bars=9,
    wm_shield_distance=0.0,
    steep_line_reentry=False,
    steep_line_proximity=0.0,
    steep_line_exit_only=False,
)

files = json.loads(sys.argv[1])
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

for batch_start in range(0, total, BATCH_SIZE):
    batch_end = min(batch_start + BATCH_SIZE, total)
    batch_files = csv_files[batch_start:batch_end]
    try:
        result = subprocess.run(
            [sys.executable, "-c", WORKER_SCRIPT, json.dumps(batch_files)],
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
            processed += len(batch_results)
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    pct = int(batch_end / total * 100)
    print(f"  [{batch_end}/{total}] {pct}%", flush=True)

elapsed = time.time() - t_start

print(f"\n{'='*80}")
print(f"BACKTEST: warmup=8, NO partial TP (partial_tp_pts=0)")
print(f"{'='*80}")
print(f"Days processed: {processed}, Time: {elapsed:.1f}s\n")
print(f"{'End Time':<12} {'Days':>7} {'Win':>8} {'Lose':>7} {'Win%':>6} {'Pts':>10} {'Avg/Day':>8}")
print(f"{'-'*70}")
for et in DAY_END_TIMES:
    t = totals[et]
    tr = t["trades"]
    wr = t["winners"]/tr*100 if tr else 0
    avg = np.mean(t["daily_pls"]) if t["daily_pls"] else 0
    print(f"{et:<12} {tr:>7} {t['winners']:>8} {t['losers']:>7} {wr:>5.1f}% {t['pl']:>10.0f} {avg:>+7.1f}")

print(f"\nWith TP @50 on High: 10:30=+23.1, 14:00=+22.7, 17:00=-3.8")
print(f"With TP @50 on Close (warmup=8): 10:30=+27.7, 14:00=+31.1, 17:00=+6.3")
