import os
import pandas as pd
import pytz
import numpy as np
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.expanduser("~/Desktop/2YearsData/full_day")

config = AlgoConfig(
    warmup_minutes=12,
    steep_angle_threshold=70.0,
    proximity_points=15.0,
    min_reversal_minutes=10,
    min_entry_angle=30.0,
    partial_tp_pts=50.0,
)

d = '2026-02-24'
fpath = os.path.join(_DATA_ROOT, f"CBOT_MINI_YM1_{d}.csv")
df = pd.read_csv(fpath, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)

start_ts = pd.Timestamp(f"{d} 09:30", tz=_EST)
end_ts   = pd.Timestamp(f"{d} 10:30", tz=_EST)
day_data = df[(df.index >= start_ts) & (df.index <= end_ts)]

result = run_trading_algo_fast(day_data, d, "09:30", "10:30", config=config)

# Print bar-by-bar from 9:30 to 9:50 showing rays, angles, price action
print(f"{'Time':<8} {'Close':>7} {'Purple':>8} {'Blue':>8} {'P_ang':>7} {'B_ang':>7} {'Signal':<8} {'Position':<8}")
print("-" * 70)
for ts, row in result.iterrows():
    t = ts.strftime('%H:%M')
    if t > '09:55':
        break
    sig = str(row.get('signal', ''))
    pos = str(row.get('position', ''))
    close = row['Close']
    purple = row.get('purple_ray', np.nan)
    blue   = row.get('blue_ray', np.nan)
    p_ang  = row.get('purple_angle', np.nan)
    b_ang  = row.get('blue_angle', np.nan)

    flag = ' <-- SIGNAL' if sig in ('BUY', 'SELL') else ''
    print(f"{t:<8} {close:>7.0f} {purple:>8.0f} {blue:>8.0f} {p_ang:>7.1f} {b_ang:>7.1f} {sig:<8} {pos:<8}{flag}")
