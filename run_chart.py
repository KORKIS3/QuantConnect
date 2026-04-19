"""Quick interactive chart from local CSV data. No IB needed.
Usage: python run_chart.py 2026-02-23 09:30 10:30
"""
import sys, os
import pandas as pd, pytz
import matplotlib
matplotlib.use("TkAgg")
from TradingAlgo import run_trading_algo, AlgoConfig
from Plotter import plot_results

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

date = sys.argv[1] if len(sys.argv) > 1 else "2026-02-23"
start_t = sys.argv[2] if len(sys.argv) > 2 else "09:30"
end_t = sys.argv[3] if len(sys.argv) > 3 else "10:30"

fname = os.path.join(_DATA_ROOT, f"CBOT_MINI_YM1_{date}.csv")
df = pd.read_csv(fname, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)

ds = pd.Timestamp(f"{date} {start_t}", tz=_EST)
de = pd.Timestamp(f"{date} {end_t}", tz=_EST)
df = df[(df.index >= ds) & (df.index <= de)]

config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=10,
                    max_loss_per_trade=999, line_tolerance=500.0)  # 999 disables trailing stop
algo_df = run_trading_algo(df, date, start_t, end_t, config=config)
plot_results(algo_df, date, start_t, end_t)
