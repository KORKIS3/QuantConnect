"""Interactive chart for May 11, 2026."""

import os
import pandas as pd
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast
from plotFigure import ChartPlotter

# Path to yesterday's data
data_path = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day", "CBOT_MINI_YM1_2026-05-11.csv")

if not os.path.exists(data_path):
    print(f"Data file not found: {data_path}")
    print("Checking if file exists with different name...")
    data_dir = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
    files = [f for f in os.listdir(data_dir) if "2026-05-11" in f or "2026_05_11" in f]
    if files:
        print(f"Found: {files}")
        data_path = os.path.join(data_dir, files[0])
    else:
        print("No data file found for 2026-05-11")
        exit(1)

print(f"Loading data from: {data_path}")
df = pd.read_csv(data_path, parse_dates=['time'])
df = df.set_index('time')

# Filter to day session only (9:30-17:00 ET)
import pytz
est = pytz.timezone("US/Eastern")
if df.index.tz is None:
    df.index = df.index.tz_localize(est)
else:
    df.index = df.index.tz_convert(est)

day_start = pd.Timestamp("2026-05-11 09:30:00", tz=est)
day_end = pd.Timestamp("2026-05-11 17:00:00", tz=est)
df = df[(df.index >= day_start) & (df.index <= day_end)]

print(f"Loaded {len(df)} bars from {df.index[0]} to {df.index[-1]}")

# Use current proven config
cfg = AlgoConfig(
    warmup_minutes=12,
    steep_angle_threshold=70.0,
    proximity_points=15.0,
    min_reversal_minutes=0,
    min_entry_angle=30.0,
    partial_tp_pts=50.0,
    wm_shield_distance=12.0,
    steep_line_threshold=50.0,  # Back to default
)




print("Running algo...")
result = run_trading_algo_fast(df, target_date="2026-05-11", config=cfg)

# Check cutoff time
cutoff_time = pd.Timestamp("2026-05-11 09:42:00", tz="US/Eastern")
cutoff_idx = None
for i, t in enumerate(result.index):
    if t >= cutoff_time:
        cutoff_idx = i
        break
print(f"Cutoff index: {cutoff_idx}, time: {result.index[cutoff_idx] if cutoff_idx else 'N/A'}")

print(f"Algo complete. Final P/L: {result['pl'].iloc[-1]:.0f} pts")
print(f"Position: {result['position'].iloc[-1]}")

# Check purple ray and touch points around 9:36-9:45
print("\nPurple ray analysis around 9:30-9:45:")
for t in pd.date_range("2026-05-11 09:30", "2026-05-11 09:45", freq="1min", tz="US/Eastern"):
    if t in result.index:
        row = result.loc[t]
        # Check if there's a steep line at this bar
        has_steep = "YES" if not pd.isna(row['purple_steep_0_vals']) else "no"
        print(f"{t.strftime('%H:%M')}: High={row['High']:.0f}, Purple={row['purple_ray']:.0f}, Slope={row['purple_slope']:.6f}, Diff={row['purple_ray']-row['High']:.0f}, Steep={has_steep}")


# Check if steep lines were generated
print("\nSteep line check:")
print("Purple steep lines:")
for li in range(4):
    col = f"purple_steep_{li}_vals"
    if col in result.columns:
        non_nan = result[col].dropna()
        if not non_nan.empty:
            print(f"  Steep {li}: {len(non_nan)} bars, first at {non_nan.index[0].strftime('%H:%M')}")
        else:
            print(f"  Steep {li}: no data")

print("\nBlue steep lines:")
for li in range(4):
    col = f"blue_steep_{li}_vals"
    if col in result.columns:
        non_nan = result[col].dropna()
        if not non_nan.empty:
            print(f"  Steep {li}: {len(non_nan)} bars, first at {non_nan.index[0].strftime('%H:%M')}")
        else:
            print(f"  Steep {li}: no data")






# Show interactive chart
print("Opening interactive chart...")
plotter = ChartPlotter(
    result, 
    target_date="2026-05-11",
    start_time="09:30",
    end_time="17:00",
    output_dir=os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "charts")
)
plotter.show()
