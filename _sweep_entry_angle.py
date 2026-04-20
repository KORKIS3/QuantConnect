"""Sweep min_entry_angle to find best value vs sim days."""
import os, pandas as pd, pytz
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig

_EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1000")
sim = pd.read_csv(os.path.join("SIM", "sim_trade_analysis.csv"))
sim_pts = [int(str(r).replace("+","").replace(",","")) for r in sim["total_pl_pts"]]
sim_total = sum(sim_pts)
dates = list(sim["date"].astype(str))

print(f"Sim total: {sim_total:+d} pts  ({sim_total/len(dates):+.1f}/day)\n")
print(f"{'angle':>6} {'total':>8} {'avg/day':>8} {'gap/day':>8}")
print("-" * 35)

best = -9999; best_angle = 0
for angle in [0, 30, 35, 40, 45, 50, 55, 60]:
    cfg = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                     proximity_points=15.0, min_reversal_minutes=10,
                     min_entry_angle=float(angle))
    total = 0; n = 0
    for date in dates:
        fname = os.path.join(DATA_ROOT, f"CBOT_MINI_YM1_{date}.csv")
        if not os.path.exists(fname): continue
        df = pd.read_csv(fname, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        try:
            r = run_trading_algo_fast(df, date, "09:30", "10:30", config=cfg)
            total += float(r["pl"].iloc[-1]); n += 1
        except: pass
    avg = total/n if n else 0
    gap = avg - sim_total/len(dates)
    marker = " ←" if total > best else ""
    if total > best: best = total; best_angle = angle
    print(f"{angle:>6} {total:>+8.0f} {avg:>+8.1f} {gap:>+8.1f}{marker}")

print(f"\nBest: min_entry_angle={best_angle}")
