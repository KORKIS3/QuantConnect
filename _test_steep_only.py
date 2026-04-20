import os, pandas as pd, pytz
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig
_EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1000")

cfg_base  = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0, proximity_points=15.0, min_reversal_minutes=10)
cfg_steep = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0, proximity_points=15.0, min_reversal_minutes=10, min_entry_angle=30.0)

dates = ["2026-02-03","2026-02-04","2026-02-05","2026-02-09","2026-02-10","2026-02-11","2026-02-13","2026-02-18","2026-02-17"]
sim_pts = [275, 212, 129, 116, -61, 226, 16, 155, -6]

print(f"{'DATE':<12} {'SIM':>6} {'BASE':>6} {'STEEP':>7} {'DIFF':>6}")
print("-" * 45)
total_base = 0; total_steep = 0; total_sim = 0
for date, sim in zip(dates, sim_pts):
    fname = os.path.join(DATA_ROOT, f"CBOT_MINI_YM1_{date}.csv")
    if not os.path.exists(fname): continue
    df = pd.read_csv(fname, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    r_base  = run_trading_algo_fast(df, date, "09:30", "10:30", config=cfg_base)
    r_steep = run_trading_algo_fast(df, date, "09:30", "10:30", config=cfg_steep)
    base_pl  = float(r_base["pl"].iloc[-1])
    steep_pl = float(r_steep["pl"].iloc[-1])
    diff = steep_pl - base_pl
    total_base += base_pl; total_steep += steep_pl; total_sim += sim
    marker = " +" if steep_pl > base_pl else (" -" if steep_pl < base_pl else "")
    print(f"{date:<12} {sim:>+6} {base_pl:>+6.0f} {steep_pl:>+7.0f} {diff:>+6.0f}{marker}")

print("-" * 45)
print(f"{'TOTAL':<12} {total_sim:>+6} {total_base:>+6.0f} {total_steep:>+7.0f} {total_steep-total_base:>+6.0f}")
print(f"Avg gap base:  {(total_base-total_sim)/len(dates):>+.1f} pts/day")
print(f"Avg gap steep: {(total_steep-total_sim)/len(dates):>+.1f} pts/day")
