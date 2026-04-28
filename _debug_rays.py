import os, pandas as pd, pytz
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig
_EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
date = "2026-04-06"; start_t = "09:30"; end_t = "11:30"
df = pd.read_csv(os.path.join(DATA_ROOT, f"CBOT_MINI_YM1_{date}.csv"), index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
df = df[(df.index >= pd.Timestamp(f"{date} {start_t}", tz=_EST)) & (df.index <= pd.Timestamp(f"{date} {end_t}", tz=_EST))]
config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0, proximity_points=15.0, min_reversal_minutes=0, min_entry_angle=30.0)
r = run_trading_algo_fast(df, date, start_t, end_t, config=config)

print(f"{'Time':<6} {'Close':>8} {'blue_ray':>8} {'blue_start':>10} {'blue_end':>8} {'BlueAng':>8} {'Signal'}")
for i in range(20):
    row = r.iloc[i]
    t = r.index[i].strftime("%H:%M")
    ba = row["blue_angle"][i] if isinstance(row["blue_angle"], list) else float(row["blue_angle"])
    sig = row["signal"] if row["signal"] else ""
    print(f"{t:<6} {row['Close']:>8.0f} {row['blue_ray']:>8.0f} {row['blue_ray_start_price']:>10.0f} {row['blue_ray_end_price']:>8.0f} {ba:>8.1f} {sig}")
