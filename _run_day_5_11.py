"""Run May 11, 2026 day session with full interactive chart."""

import os
import pandas as pd
import pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast
from plotFigure import ChartPlotter

# Load data
data_path = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day", "CBOT_MINI_YM1_2026-05-11.csv")
df = pd.read_csv(data_path, parse_dates=['time'])
df = df.set_index('time')

# Filter to day session (9:30-17:00 ET)
est = pytz.timezone("US/Eastern")
if df.index.tz is None:
    df.index = df.index.tz_localize(est)
else:
    df.index = df.index.tz_convert(est)

day_start = pd.Timestamp("2026-05-11 09:30:00", tz=est)
day_end = pd.Timestamp("2026-05-11 17:00:00", tz=est)
df = df[(df.index >= day_start) & (df.index <= day_end)]

print(f"Loaded {len(df)} bars for day session (9:30-17:00)")

# Run algo with current config
cfg = AlgoConfig(
    warmup_minutes=12,
    steep_angle_threshold=70.0,
    proximity_points=15.0,
    min_reversal_minutes=0,
    min_entry_angle=30.0,
    partial_tp_pts=50.0,
    wm_shield_distance=12.0,
)

result = run_trading_algo_fast(
    df, 
    target_date="2026-05-11",
    start_time="09:30",
    end_time="17:00",
    config=cfg
)

print(f"Algo complete. Final P/L: {result['session_pl'].iloc[-1]:.0f} pts")

# Open full interactive chart
output_dir = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "charts")
plotter = ChartPlotter(
    result,
    target_date="2026-05-11",
    start_time="09:30",
    end_time="17:00",
    output_dir=output_dir
)
plotter.show()
