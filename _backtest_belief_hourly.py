"""Full backtest: Belief Engine v1 — hourly P/L breakdown."""
import subprocess, sys, os, json, time
import numpy as np

DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
csv_files = sorted([f for f in os.listdir(DATA_ROOT) if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])
total = len(csv_files)
BATCH_SIZE = 25

END_TIMES = ["10:00", "10:30", "11:00", "11:30", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00"]

t_start = time.time()

# Collect P/L at each end time
hourly_pls = {et: [] for et in END_TIMES}

WORKER_SCRIPT = '''
import sys, os, json
sys.path.insert(0, '.')
import pandas as pd, pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast
from fred_belief_engine import BeliefEngine

EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
END_TIMES = ["10:00", "10:30", "11:00", "11:30", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00"]

CONFIG = AlgoConfig(
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

        algo_df = run_trading_algo_fast(day_data, target_date, "09:30", "17:00", config=CONFIG)
        engine = BeliefEngine()
        belief_log = engine.run_session(algo_df)

        if len(belief_log) > 0:
            day_results = {}
            for et in END_TIMES:
                end_ts = pd.Timestamp(f"{target_date} {et}", tz=EST)
                sliced = belief_log[belief_log["time"] <= end_ts]
                if len(sliced) > 0:
                    day_results[et] = float(sliced.iloc[-1]["session_pl"])
            if day_results:
                results[target_date] = day_results
    except Exception:
        continue

print(json.dumps(results))
'''

print(f"BELIEF ENGINE v1 — HOURLY BREAKDOWN")
print(f"Files: {total}, Batch size: {BATCH_SIZE}")
print("=" * 80)

for batch_start in range(0, total, BATCH_SIZE):
    batch_end = min(batch_start + BATCH_SIZE, total)
    batch_files = csv_files[batch_start:batch_end]
    try:
        result = subprocess.run(
            [sys.executable, "-c", WORKER_SCRIPT, json.dumps(batch_files)],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode == 0 and result.stdout.strip():
            batch_results = json.loads(result.stdout.strip())
            for date_str, day_pls in batch_results.items():
                for et, pl in day_pls.items():
                    if et in hourly_pls:
                        hourly_pls[et].append(pl)
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    pct = int(batch_end / total * 100)
    print(f"  [{batch_end}/{total}] {pct}%", flush=True)

elapsed = time.time() - t_start

print(f"\n{'='*80}")
print(f"BELIEF ENGINE v1 — HOURLY P/L BREAKDOWN")
print(f"{'='*80}")
print(f"Time: {elapsed:.0f}s\n")
print(f"{'End Time':<10} {'Days':<6} {'Win':<6} {'Lose':<6} {'Win%':<7} {'Total Pts':<12} {'Avg/Day':<10} {'Median':<8}")
print("-" * 75)

for et in END_TIMES:
    pls = hourly_pls[et]
    if not pls:
        print(f"{et:<10} 0")
        continue
    n = len(pls)
    w = sum(1 for x in pls if x > 0)
    l = sum(1 for x in pls if x < 0)
    wr = w / (w + l) * 100 if (w + l) > 0 else 0
    total_pl = sum(pls)
    avg = np.mean(pls)
    med = np.median(pls)
    print(f"{et:<10} {n:<6} {w:<6} {l:<6} {wr:<6.1f}% {total_pl:<12.0f} {avg:<+10.1f} {med:<+8.0f}")
