"""Fine-tune tolerance sweep: 50-500."""
import os
import pandas as pd, pytz, numpy as np
from TradingAlgo import AlgoConfig
from test_tolerance import run_fast_with_tolerance, run_bt_with_algo, find_clusters

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0, max_loss_per_trade=0)
csv_files = sorted([f for f in os.listdir(_DATA_ROOT) if f.endswith(".csv")])
print(f"Fine tolerance sweep on {len(csv_files)} days\n", flush=True)

_MUL = 5

tolerances = [75, 100, 150, 200, 300, 500]

hdr = f"{'Tolerance':>12} {'Total USD':>14} {'Pts/c/day':>10} {'Win%':>6} {'Worst':>10} {'Best':>10}"
print(hdr)
print("-" * len(hdr))

for tol in tolerances:
    agg_pts = 0.0; daily_pls = []; wins = 0; losses = 0
    for fname in csv_files:
        dd = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
        try:
            df = pd.read_csv(os.path.join(_DATA_ROOT, fname), index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        except: continue
        if len(df) < 10: continue
        ds = pd.Timestamp(f"{dd} 09:30", tz=_EST)
        de = pd.Timestamp(f"{dd} 17:00", tz=_EST)
        dd_data = df[(df.index >= ds) & (df.index <= de)]
        if len(dd_data) < 15: continue
        try:
            algo = run_fast_with_tolerance(dd_data, dd, "09:30", "17:00", config, tol)
        except: continue
        day_pts = run_bt_with_algo(algo)
        if day_pts is not None:
            agg_pts += day_pts
            daily_pls.append(day_pts)
            if day_pts > 0: wins += 1
            else: losses += 1

    n = len(daily_pls) if daily_pls else 1
    total_usd = agg_pts * _MUL
    avg_pts_cd = agg_pts / 2 / n
    win_pct = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
    worst = min(daily_pls) if daily_pls else 0
    best = max(daily_pls) if daily_pls else 0
    print(f"{tol:>12} ${total_usd:>+12,.0f} {avg_pts_cd:>+9.1f} {win_pct:>5.1f}% {worst:>+9.0f} pts {best:>+9.0f} pts", flush=True)

print(f"\nBaseline (regression): $+757,105  +143.4 pts/c/day")
