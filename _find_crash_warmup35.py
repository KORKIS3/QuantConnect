"""Find which file crashes with warmup_minutes=35 by testing around position 338."""
import subprocess, sys, os

DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
csv_files = sorted([f for f in os.listdir(DATA_ROOT) if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])

# Test files 335-345 individually in subprocesses
for i in range(335, min(350, len(csv_files))):
    fname = csv_files[i]
    script = f"""
import sys, os; sys.path.insert(0, '.')
import faulthandler; faulthandler.enable()
import pandas as pd, pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast
EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
fname = "{fname}"
target_date = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
fpath = os.path.join(DATA_ROOT, fname)
df = pd.read_csv(fpath, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(EST)
day_start = pd.Timestamp(f"{{target_date}} 09:30", tz=EST)
day_end = pd.Timestamp(f"{{target_date}} 16:59", tz=EST)
day_data = df[(df.index >= day_start) & (df.index <= day_end)]
if len(day_data) < 15 or day_data["Volume"].sum() < 100:
    print("SKIP")
    sys.exit(0)
config = AlgoConfig(warmup_minutes=35, steep_angle_threshold=65.0, proximity_points=8.0, min_reversal_minutes=0, min_entry_angle=15.0, partial_tp_pts=50.0, spike_profit_pts=50.0, spike_profit_bars=9, wm_shield_distance=0.0, steep_line_reentry=False, steep_line_proximity=0.0, steep_line_exit_only=False)
run_trading_algo_fast(day_data, target_date, "09:30", "17:00", config=config)
print("OK")
"""
    try:
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, timeout=30, text=True)
        status = "OK" if result.returncode == 0 else f"CRASH (rc={result.returncode})"
        if result.returncode != 0:
            print(f"[{i}] {fname}: {status}")
            if result.stderr:
                print(f"    stderr: {result.stderr[:200]}")
        else:
            print(f"[{i}] {fname}: {result.stdout.strip()}")
    except subprocess.TimeoutExpired:
        print(f"[{i}] {fname}: TIMEOUT")
