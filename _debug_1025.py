import os
import pandas as pd
import pytz
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.expanduser("~/Desktop/2YearsData/full_day")

d = "2026-04-23"
config = AlgoConfig(
    warmup_minutes=12, steep_angle_threshold=70.0, proximity_points=15.0,
    min_reversal_minutes=0, min_entry_angle=30.0, partial_tp_pts=50.0,
)

df = pd.read_csv(os.path.join(_DATA_ROOT, f"CBOT_MINI_YM1_{d}.csv"), index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
start_ts = pd.Timestamp(f"{d} 09:30", tz=_EST)
end_ts   = pd.Timestamp(f"{d} 17:00", tz=_EST)
day_data = df[(df.index >= start_ts) & (df.index <= end_ts)]
result   = run_trading_algo_fast(day_data, d, "09:30", "17:00", config=config)

print(f"{'Time':<8} {'Close':>7} {'Purple':>8} {'Blue':>8} {'P_ang':>7} {'B_ang':>7} {'Signal':<8} {'Pos':<8}")
print("-" * 70)
for ts, row in result.iterrows():
    t = ts.strftime('%H:%M')
    if t < '10:15' or t > '10:55':
        continue
    sig = str(row.get('signal', ''))
    pos = str(row.get('position', ''))
    flag = ' <-- SIGNAL' if sig in ('BUY','SELL') else ''
    print(f"{t:<8} {row['Close']:>7.0f} {row['purple_ray']:>8.0f} {row['blue_ray']:>8.0f} "
          f"{row.get('purple_angle',0):>7.1f} {row.get('blue_angle',0):>7.1f} {sig:<8} {pos:<8}{flag}")
