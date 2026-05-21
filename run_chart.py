"""Quick interactive chart from local CSV data. No IB needed.
Usage: python run_chart.py 2025-04-07 09:30 17:00
       python run_chart.py 2026-03-31
"""
import sys, os
import pandas as pd, pytz
import matplotlib
matplotlib.use("TkAgg")

from TradingAlgoFast import run_trading_algo_fast, AlgoConfig
from plotFigure import plot_intraday_data

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

date = sys.argv[1] if len(sys.argv) > 1 else "2026-03-31"
start_t = sys.argv[2] if len(sys.argv) > 2 else "09:30"
end_t = sys.argv[3] if len(sys.argv) > 3 else "17:00"

fname = os.path.join(_DATA_ROOT, f"CBOT_MINI_YM1_{date}.csv")
if not os.path.exists(fname):
    print(f"File not found: {fname}")
    sys.exit(1)

df = pd.read_csv(fname, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)

ds = pd.Timestamp(f"{date} {start_t}", tz=_EST)
de = pd.Timestamp(f"{date} {end_t}", tz=_EST)
df = df[(df.index >= ds) & (df.index <= de)]

print(f"Running chart for {date} {start_t}-{end_t} ({len(df)} bars)...")

config = AlgoConfig(
    warmup_minutes=7, steep_angle_threshold=90.0, proximity_points=4.0,
    min_reversal_minutes=0, min_entry_angle=0.0, partial_tp_pts=50.0,
    wm_shield_distance=0.0, swing_anchor_threshold=10.0,
)

algo_df = run_trading_algo_fast(df, date, start_t, end_t, config=config)
print(f"Session P/L: {algo_df['session_pl'].iloc[-1]:+.0f} pts")

plot_intraday_data(algo_df, date, start_t, end_t)
