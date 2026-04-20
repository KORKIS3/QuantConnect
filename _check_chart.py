import os, pandas as pd, pytz, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig
from plotFigure import ChartPlotter

_EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1000")
OUT = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "charts")
os.makedirs(OUT, exist_ok=True)

date = "2026-02-23"
start_t = "09:30"
end_t = "10:30"

fname = os.path.join(DATA_ROOT, f"CBOT_MINI_YM1_{date}.csv")
df = pd.read_csv(fname, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=False)
if df.index.tz is None:
    df.index = df.index.tz_localize(_EST)
else:
    df.index = df.index.tz_convert(_EST)

config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0, proximity_points=15.0, min_reversal_minutes=10)
algo_df = run_trading_algo_fast(df, date, start_t, end_t, config=config)

img_path = os.path.join(OUT, f"YM_{date}_check.jpg")
plotter = ChartPlotter(algo_df, date, start_t, end_t, output_dir="", batch_mode=True)
plotter.create_figure()
plotter.update_plot(len(algo_df) - 1)
plotter.fig.savefig(img_path, dpi=150, bbox_inches="tight")
plt.close(plotter.fig)
print(f"Saved: {img_path}")
pl = algo_df["pl"].iloc[-1]
print(f"P/L: {pl:+.0f} pts")
