"""Check if min_entry_angle=30 and 35 produce identical results."""
import os, pandas as pd, pytz
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig

_EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1000")
files = sorted([f for f in os.listdir(DATA_ROOT) if f.endswith(".csv")])

configs = {
    "angle=0 ": AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0, proximity_points=15.0, min_reversal_minutes=10, min_entry_angle=0.0),
    "angle=30": AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0, proximity_points=15.0, min_reversal_minutes=10, min_entry_angle=30.0),
    "angle=35": AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0, proximity_points=15.0, min_reversal_minutes=10, min_entry_angle=35.0),
    "angle=40": AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0, proximity_points=15.0, min_reversal_minutes=10, min_entry_angle=40.0),
}

totals = {k: 0.0 for k in configs}
diffs_30_35 = []
n = 0

for fname in files:
    date = fname.replace("CBOT_MINI_YM1_","").replace(".csv","")
    df = pd.read_csv(os.path.join(DATA_ROOT, fname), index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    if len(df) < 10: continue
    pls = {}
    try:
        for k, cfg in configs.items():
            r = run_trading_algo_fast(df, date, "09:30", "10:30", config=cfg)
            pls[k] = float(r["pl"].iloc[-1])
            totals[k] += pls[k]
        # Track days where 30 and 35 differ
        if pls["angle=30"] != pls["angle=35"]:
            diffs_30_35.append((date, pls["angle=30"], pls["angle=35"], pls["angle=30"]-pls["angle=35"]))
        n += 1
    except: pass

print(f"Tested {n} days (9:30-10:30)\n")
print(f"{'Config':<10} {'Total Pts':>10} {'Avg/Day':>8}")
print("-" * 32)
for k, t in totals.items():
    print(f"{k:<10} {t:>+10.0f} {t/n:>+8.1f}")

print(f"\nDays where angle=30 and angle=35 DIFFER: {len(diffs_30_35)}")
if diffs_30_35:
    print(f"{'Date':<12} {'30':>8} {'35':>8} {'Diff':>8}")
    for d, p30, p35, diff in diffs_30_35[:20]:
        print(f"{d:<12} {p30:>+8.0f} {p35:>+8.0f} {diff:>+8.0f}")
else:
    print("  -> They are IDENTICAL on all days")
