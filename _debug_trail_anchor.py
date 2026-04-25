"""
Debug the trailing stop anchor and line value at 10:20 on 4/23
to understand why it fired at the top of a strong move.
"""
import os
import numpy as np
import pandas as pd
import pytz
import matplotlib.dates as mdates
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig, _compute_rays_nb

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

highs  = day_data["High"].values.astype(np.float64)
lows   = day_data["Low"].values.astype(np.float64)
closes = day_data["Close"].values.astype(np.float64)
times  = day_data.index
times_num = np.array([mdates.date2num(t) for t in times])

_ax_w_in = 16.0 * (0.85 - 0.125)
_ax_h_in = 9.0  * (0.88 - 0.11)
_x_range = 75 / (24 * 60)
_y_range = highs.max() + 20.0 - (lows.min() - 20.0)
x_per_unit = _x_range / _ax_w_in
y_per_unit = _y_range / _ax_h_in

# Entry at 10:11 bar index
entry_bar = list(times.strftime('%H:%M')).index('10:11')
entry_price = closes[entry_bar]
print(f"Entry bar: {entry_bar} ({times[entry_bar].strftime('%H:%M')}) @ {entry_price:.0f}")

# Simulate trailing stop from entry to 10:25
trail_anchor_p = -1e30
trail_anchor_t = 0.0

print(f"\n{'Time':<8} {'Close':>7} {'Unreal':>8} {'Anchor':>8} {'TrailVal':>10} {'Fired'}")
print("-" * 60)

for i in range(entry_bar, entry_bar + 15):
    if i >= len(closes): break
    t = times[i].strftime('%H:%M')
    close = closes[i]
    unreal = close - entry_price

    if unreal >= 50.0:
        trail_angle = 50.0
        trailing_slope = np.tan(np.deg2rad(trail_angle)) * (y_per_unit / x_per_unit)

        if trail_anchor_p < -1e29:
            start_j = max(entry_bar, i - 15)
            best_lo = -1e30
            for j in range(start_j, i):
                if j == 0 or j >= len(lows) - 1: continue
                lo = lows[j]
                if lows[j-1] - lo >= 10.0 and lows[j+1] - lo >= 10.0:
                    if lo > best_lo:
                        best_lo = lo
                        trail_anchor_p = lo
                        trail_anchor_t = times_num[j]
            if trail_anchor_p < -1e29:
                trail_anchor_p = lows[entry_bar]
                trail_anchor_t = times_num[entry_bar]
            print(f"  --> Anchor locked at {trail_anchor_p:.0f} ({times[list(times_num).index(trail_anchor_t) if trail_anchor_t in times_num else entry_bar].strftime('%H:%M') if trail_anchor_t > 0 else 'entry'})")

        trail_val = trail_anchor_p + trailing_slope * (times_num[i] - trail_anchor_t) if trail_anchor_t > 0 else 0
        fired = "*** FIRED ***" if close < trail_val else ""
        print(f"{t:<8} {close:>7.0f} {unreal:>+8.0f} {trail_anchor_p:>8.0f} {trail_val:>10.0f} {fired}")
    else:
        print(f"{t:<8} {close:>7.0f} {unreal:>+8.0f} {'--':>8} {'--':>10}")
