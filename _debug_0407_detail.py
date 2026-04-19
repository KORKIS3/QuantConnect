"""Debug 04/07/25 around 9:53-9:54."""
import os
import pandas as pd, pytz, numpy as np
from TradingAlgo import AlgoConfig
from TradingAlgoFast import run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0,
                    max_loss_per_trade=0, line_tolerance=500.0)

df = pd.read_csv(os.path.join(_DATA_ROOT, "CBOT_MINI_YM1_2025-04-07.csv"), index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
ds = pd.Timestamp("2025-04-07 09:30", tz=_EST)
de = pd.Timestamp("2025-04-07 17:00", tz=_EST)
dd_data = df[(df.index >= ds) & (df.index <= de)]
algo = run_trading_algo_fast(dd_data, "2025-04-07", "09:30", "17:00", config=config)

# Show bars 9:40-10:05 with all ray values
print("Time   Close   Purple  Blue    Orange  Yellow  Signal")
print("-" * 70)
for ts, row in algo.iterrows():
    t = ts.strftime("%H:%M")
    if t < "09:40" or t > "10:05": continue
    c = row["Close"]; p = row["purple_ray"]; b = row["blue_ray"]
    o = row["orange_ray"]; y = row["yellow_ray"]
    sig = str(row["signal"]) if pd.notna(row["signal"]) and row["signal"] != "" else ""
    flag = " <--" if sig else ""
    print(f"{t}   {c:.0f}   {p:.0f}   {b:.0f}   {o:.0f}   {y:.0f}   {sig}{flag}")
