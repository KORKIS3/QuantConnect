"""Run today's day session backtest replay and save chart + CSV.
Run this after 17:00 ET each trading day.
Usage: python run_today.py
       python run_today.py 2025-09-22  (specific date)
"""
import sys, os
from datetime import date
import pandas as pd, pytz
import matplotlib
matplotlib.use("Agg")  # headless for saving image
import matplotlib.pyplot as plt
from TradingAlgo import run_trading_algo, AlgoConfig
from plotFigure import ChartPlotter

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
_OUT_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "charts")
os.makedirs(_OUT_DIR, exist_ok=True)

# Date: today or specified
target_date = sys.argv[1] if len(sys.argv) > 1 else date.today().strftime("%Y-%m-%d")
start_t = "09:30"; end_t = "17:00"

fname = os.path.join(_DATA_ROOT, f"CBOT_MINI_YM1_{target_date}.csv")
if not os.path.exists(fname):
    print(f"No data file found for {target_date}: {fname}")
    print("Make sure the CSV exists in ~/Desktop/2YearsData/full_day/")
    sys.exit(1)

print(f"Running backtest replay for {target_date}...")
df = pd.read_csv(fname, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
ds = pd.Timestamp(f"{target_date} {start_t}", tz=_EST)
de = pd.Timestamp(f"{target_date} {end_t}", tz=_EST)
df = df[(df.index >= ds) & (df.index <= de)]

if len(df) < 15:
    print(f"Not enough data for {target_date} ({len(df)} bars)")
    sys.exit(1)

config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=10)
algo_df = run_trading_algo(df, target_date, start_t, end_t, config=config)

# P/L summary
final_pl = float(algo_df["pl"].iloc[-1])
signals = algo_df[algo_df["signal"].isin(["BUY","SELL"])]
print(f"\n=== {target_date} Day Session ===")
print(f"Final P/L: {final_pl:+.0f} pts  /  ${final_pl*5*2:+,.0f}  (2 contracts)")
print(f"Signals: {len(signals)}")
for ts, row in signals.iterrows():
    sig = row["signal"]
    price = row["buy_price"] if sig == "BUY" else row["sell_price"]
    pl = row["pl"]
    print(f"  {ts.strftime('%H:%M')}  {sig:4s} @ {int(price)}   P/L: {pl:+.0f} pts")

# Save CSV
csv_path = os.path.join(_OUT_DIR, f"YM_{target_date}_0930_1700.csv")
algo_df.to_csv(csv_path)
print(f"\nCSV saved: {csv_path}")

# Save chart image (full day, all bars visible)
img_path = os.path.join(_OUT_DIR, f"YM_{target_date}_0930_1700.jpg")
plotter = ChartPlotter(algo_df, target_date, start_t, end_t, output_dir="", batch_mode=True)
plotter.create_figure()
plotter.update_plot(len(algo_df) - 1)
plotter.fig.savefig(img_path, dpi=150, bbox_inches="tight")
plt.close(plotter.fig)
print(f"Chart image saved: {img_path}")
print(f"\nFiles saved to: {_OUT_DIR}")
