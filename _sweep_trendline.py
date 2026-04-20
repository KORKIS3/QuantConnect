"""Sweep max_trendline_bars and min_cross_pts to find best combo vs sim days."""
import os, pandas as pd, pytz
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig

_EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1000")
SIM_CSV = os.path.join("SIM", "sim_trade_analysis.csv")
sim = pd.read_csv(SIM_CSV)

def run_combo(max_bars, min_cross):
    cfg = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                     proximity_points=15.0, min_reversal_minutes=10,
                     max_trendline_bars=max_bars, min_cross_pts=min_cross)
    total_algo = 0; days = 0
    for _, row in sim.iterrows():
        date = str(row["date"])
        fname = os.path.join(DATA_ROOT, f"CBOT_MINI_YM1_{date}.csv")
        if not os.path.exists(fname): continue
        df = pd.read_csv(fname, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        try:
            result = run_trading_algo_fast(df, date, "09:30", "10:30", config=cfg)
            total_algo += float(result["pl"].iloc[-1])
            days += 1
        except: pass
    return total_algo, days

sim_total = sum(int(str(r).replace("+","").replace(",","")) for r in sim["total_pl_pts"])
print(f"Sim total: {sim_total:+d} pts  ({sim_total/len(sim):+.1f}/day)\n")
print(f"{'bars':>5} {'cross':>6} {'algo_total':>11} {'avg/day':>8} {'gap/day':>8}")
print("-" * 45)

best_gap = -9999; best_combo = None
for max_bars in [0, 5, 8, 10, 15, 20]:
    for min_cross in [0, 5, 10, 15, 20]:
        total, days = run_combo(max_bars, min_cross)
        avg = total / days if days else 0
        gap = avg - sim_total/len(sim)
        marker = " ←" if total > best_gap else ""
        if total > best_gap: best_gap = total; best_combo = (max_bars, min_cross)
        print(f"{max_bars:>5} {min_cross:>6} {total:>+11.0f} {avg:>+8.1f} {gap:>+8.1f}{marker}")
    print()

print(f"\nBest: max_trendline_bars={best_combo[0]}, min_cross_pts={best_combo[1]}")
