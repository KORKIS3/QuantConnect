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

print(f"{'Time':<8} {'Close':>7} {'Orange':>8} {'Purple':>8} {'Blue':>8} {'Yellow':>8} {'P_ang':>7} {'B_ang':>7} {'Signal':<8} {'Pos':<8}")
print("-" * 85)
for ts, row in result.iterrows():
    t = ts.strftime('%H:%M')
    if t < '10:10' or t > '10:25':
        continue
    sig = str(row.get('signal', ''))
    pos = str(row.get('position', ''))
    flag = ' <-- SIGNAL' if sig in ('BUY','SELL') else ''
    close   = row['Close']
    orange  = row.get('orange_ray', 0)
    purple  = row.get('purple_ray', 0)
    blue    = row.get('blue_ray', 0)
    yellow  = row.get('yellow_ray', 0)
    p_ang   = row.get('purple_angle', 0)
    b_ang   = row.get('blue_angle', 0)

    # Mark if close crossed above purple or orange
    cross = ""
    if close > purple: cross += " >PURPLE"
    if close > orange: cross += " >ORANGE"

    print(f"{t:<8} {close:>7.0f} {orange:>8.0f} {purple:>8.0f} {blue:>8.0f} {yellow:>8.0f} "
          f"{p_ang:>7.1f} {b_ang:>7.1f} {sig:<8} {pos:<8}{flag}{cross}")
