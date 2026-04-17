"""Compare original vs fast algo on a single day to find divergence."""

import pandas as pd, pytz, numpy as np
import matplotlib.dates as mdates
from TradingAlgo import run_trading_algo, AlgoConfig

est = pytz.timezone("US/Eastern")

# Pick a recent day with known results
import os
data_root = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1130")
files = sorted([f for f in os.listdir(data_root) if f.endswith(".csv")])
fname = files[-10]  # pick a day
target_date = fname.replace("CBOT_MINI_YM1_","").replace(".csv","")
print(f"Testing day: {target_date}")

df = pd.read_csv(os.path.join(data_root, fname), index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)
print(f"Bars: {len(df)}")

# Run original algo
config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0, max_loss_per_trade=0)
algo_df = run_trading_algo(df, target_date, "09:30", "10:30", config=config)

# Print original signals
print("\nORIGINAL ALGO signals:")
for ts, row in algo_df.iterrows():
    if row.get("signal") in ("BUY","SELL"):
        sig = row["signal"]
        price = float(row["buy_price"] if sig=="BUY" else row["sell_price"])
        print(f"  {ts.strftime('%H:%M')}  {sig}  @ {int(price)}")

# Print ray values at each signal bar
print("\nRay values at signal bars:")
for ts, row in algo_df.iterrows():
    if row.get("signal") in ("BUY","SELL"):
        print(f"  {ts.strftime('%H:%M')}: orange={row['orange_ray']:.1f} yellow={row['yellow_ray']:.1f} "
              f"purple={row['purple_ray']:.1f} blue={row['blue_ray']:.1f}")

# Now compute rays the same way TradingAlgoFast does and compare
print("\n--- Comparing ray computation ---")
highs  = df["High"].values.astype(np.float64)
lows   = df["Low"].values.astype(np.float64)
closes = df["Close"].values.astype(np.float64)
times  = np.array([mdates.date2num(t) for t in df.index])

# Orange ray (fast version)
fig_w, fig_h = 16.0, 9.0
ax_w_in = fig_w * (0.85 - 0.125)
ax_h_in = fig_h * (0.88 - 0.11)
x_range = 75 / (24 * 60)
y_range = highs.max() + 20 - (lows.min() - 20)
x_per_unit = x_range / ax_w_in
y_per_unit = y_range / ax_h_in

orange_angle_rad = np.deg2rad(2.5)
orange_slope = -np.tan(orange_angle_rad) * (y_per_unit / x_per_unit)

orange_fast = np.zeros(len(df))
anchor_price = highs[0]
anchor_time  = times[0]
for i in range(len(df)):
    if highs[i] > anchor_price:
        anchor_price = highs[i]
        anchor_time  = times[i]
    orange_fast[i] = anchor_price + orange_slope * (times[i] - anchor_time)

# Compare at signal bars
print("\nOrange ray comparison (original vs fast):")
for idx, (ts, row) in enumerate(algo_df.iterrows()):
    if row.get("signal") in ("BUY","SELL"):
        orig = row["orange_ray"]
        fast = orange_fast[idx]
        diff = abs(orig - fast)
        print(f"  {ts.strftime('%H:%M')}: orig={orig:.1f}  fast={fast:.1f}  diff={diff:.1f}")

# Yellow ray (fast version)
yellow_angle_rad = np.deg2rad(2.5)
yellow_slope = np.tan(yellow_angle_rad) * (y_per_unit / x_per_unit)

yellow_fast = np.zeros(len(df))
anchor_price = lows[0]
anchor_time  = times[0]
for i in range(len(df)):
    if lows[i] < anchor_price:
        anchor_price = lows[i]
        anchor_time  = times[i]
    yellow_fast[i] = anchor_price + yellow_slope * (times[i] - anchor_time)

print("\nYellow ray comparison (original vs fast):")
for idx, (ts, row) in enumerate(algo_df.iterrows()):
    if row.get("signal") in ("BUY","SELL"):
        orig = row["yellow_ray"]
        fast = yellow_fast[idx]
        diff = abs(orig - fast)
        print(f"  {ts.strftime('%H:%M')}: orig={orig:.1f}  fast={fast:.1f}  diff={diff:.1f}")


# Now check: how many signals are triggered by orange/yellow vs purple/blue?
print("\n--- Signal trigger analysis ---")
for idx in range(1, len(algo_df)):
    ts  = algo_df.index[idx]
    row = algo_df.iloc[idx]
    if row.get("signal") not in ("BUY","SELL"):
        continue
    sig = row["signal"]
    prev = algo_df.iloc[idx-1]
    prev_close = float(prev["Close"])
    curr_close = float(row["Close"])
    prev_orange = float(prev["orange_ray"])
    prev_yellow = float(prev["yellow_ray"])
    prev_purple = float(prev["purple_ray"])
    prev_blue   = float(prev["blue_ray"])

    triggers = []
    if sig == "BUY":
        if prev_close <= prev_orange and curr_close > float(row["orange_ray"]):
            triggers.append("ORANGE")
        if prev_close <= prev_purple and curr_close > float(row["purple_ray"]):
            triggers.append("PURPLE")
    elif sig == "SELL":
        if prev_close >= prev_yellow and curr_close < float(row["yellow_ray"]):
            triggers.append("YELLOW")
        if prev_close >= prev_blue and curr_close < float(row["blue_ray"]):
            triggers.append("BLUE")

    print(f"  {ts.strftime('%H:%M')}  {sig}  triggered by: {triggers if triggers else 'UNKNOWN'}")
