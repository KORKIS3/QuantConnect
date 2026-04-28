import os, pandas as pd, pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast
_EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
date = "2026-04-06"
df = pd.read_csv(os.path.join(DATA_ROOT, f"CBOT_MINI_YM1_{date}.csv"), index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
df = df[(df.index >= pd.Timestamp(f"{date} 09:30", tz=_EST)) & (df.index <= pd.Timestamp(f"{date} 11:30", tz=_EST))]
config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0, proximity_points=15.0, min_reversal_minutes=0, min_entry_angle=30.0)
r = run_trading_algo_fast(df, date, "09:30", "11:30", config=config)

print("Time   orange_ray  o_start_p  o_start_t   yellow_ray  y_start_p  y_start_t")
for i in range(0, 121, 10):
    row = r.iloc[i]
    t = r.index[i].strftime("%H:%M")
    ost = pd.Timestamp(row["orange_ray_start_time"]).strftime("%H:%M")
    yst = pd.Timestamp(row["yellow_ray_start_time"]).strftime("%H:%M")
    print(f"{t}  {row['orange_ray']:8.0f}  {row['orange_ray_start_price']:8.0f}  {ost}   {row['yellow_ray']:8.0f}  {row['yellow_ray_start_price']:8.0f}  {yst}")
