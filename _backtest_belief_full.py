"""Full backtest: Belief Engine v1 on all available days (9:30-17:00)."""
import subprocess, sys, os, json, time
import numpy as np

DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
csv_files = sorted([f for f in os.listdir(DATA_ROOT) if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])
total = len(csv_files)
BATCH_SIZE = 25  # smaller batches for belief engine (pure Python, slower)

t_start = time.time()
processed = 0
winners = 0
losers = 0
flat_days = 0
daily_pls = []

WORKER_SCRIPT = '''
import sys, os, json
sys.path.insert(0, '.')
import pandas as pd, pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast
from fred_belief_engine import BeliefEngine

EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

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

        # Run mechanical algo to get line values
        algo_df = run_trading_algo_fast(day_data, target_date, "09:30", "17:00", config=CONFIG)

        # Run belief engine
        engine = BeliefEngine()
        belief_log = engine.run_session(algo_df)

        # Get final P/L
        if len(belief_log) > 0:
            final_pl = float(belief_log.iloc[-1]["session_pl"])
            results[target_date] = final_pl
    except Exception:
        continue

print(json.dumps(results))
'''

print(f"BELIEF ENGINE v1 — FULL BACKTEST")
print(f"Files: {total}, Batch size: {BATCH_SIZE}")
print(f"Session: 9:30-17:00")
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
            for date_str, pl in batch_results.items():
                daily_pls.append(pl)
                processed += 1
                if pl > 0:
                    winners += 1
                elif pl < 0:
                    losers += 1
                else:
                    flat_days += 1
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        pass
    pct = int(batch_end / total * 100)
    print(f"  [{batch_end}/{total}] {pct}% — {processed} days processed", flush=True)

elapsed = time.time() - t_start

print(f"\n{'='*80}")
print(f"BELIEF ENGINE v1 — FULL BACKTEST RESULTS")
print(f"{'='*80}")
print(f"Days processed: {processed}")
print(f"Time: {elapsed:.0f}s")
print(f"")
print(f"Total P/L: {sum(daily_pls):.0f} pts")
print(f"Avg/Day (all): {np.mean(daily_pls):.1f} pts" if daily_pls else "N/A")
print(f"Avg/Day (traded only): {np.mean([x for x in daily_pls if x != 0]):.1f} pts" if any(x != 0 for x in daily_pls) else "N/A")
print(f"")
print(f"Win days: {winners}")
print(f"Lose days: {losers}")
print(f"Flat days (no trades): {flat_days}")
print(f"Win rate (traded days): {winners/(winners+losers)*100:.1f}%" if (winners+losers) > 0 else "N/A")
print(f"")
print(f"Max win: {max(daily_pls):.0f} pts" if daily_pls else "N/A")
print(f"Max loss: {min(daily_pls):.0f} pts" if daily_pls else "N/A")
print(f"Median: {np.median(daily_pls):.0f} pts" if daily_pls else "N/A")
