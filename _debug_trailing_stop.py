"""Trace the trailing stop logic bar by bar for the 13:13 short on 04/21."""
import pandas as pd, pytz, numpy as np, os
import matplotlib.dates as mdates
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig, _compute_rays_nb

_EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

date = "2026-04-21"
df = pd.read_csv(os.path.join(DATA_ROOT, f"CBOT_MINI_YM1_{date}.csv"), index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
ds = pd.Timestamp(f"{date} 09:30", tz=_EST)
de = pd.Timestamp(f"{date} 17:00", tz=_EST)
df = df[(df.index >= ds) & (df.index <= de)]

highs  = df["High"].values.astype(np.float64)
lows   = df["Low"].values.astype(np.float64)
closes = df["Close"].values.astype(np.float64)
times  = np.array([mdates.date2num(t) for t in df.index])
n = len(df)

_y_range = highs.max() + 20 - (lows.min() - 20)
x_per_unit = (75/(24*60)) / (16*(0.85-0.125))
y_per_unit = _y_range / (9*(0.88-0.11))

# Entry: SHORT at 13:13 @ 49,410
entry_price = 49410.0
entry_idx = df.index.get_loc(pd.Timestamp("2026-04-21 13:13:00", tz=_EST))

print(f"Short entry: 13:13 @ {entry_price}")
print(f"Entry bar index: {entry_idx}")
print()
print(f"{'Time':>6} {'Close':>7} {'Unreal':>8} {'HasHH':>6} {'Anchor':>8} {'Trail°':>7} {'StopLvl':>9} {'Fired':>6}")
print("-" * 70)

SWING_MIN = 50.0

for i in range(entry_idx + 1, min(entry_idx + 200, n)):
    ts = df.index[i]
    if ts.hour >= 16:
        break

    close = closes[i]
    unrealized = entry_price - close  # short: profit when price falls

    if unrealized < 75.0:
        continue  # trailing stop not active yet

    # Find swing high (for short position)
    has_hh = False; conf_price = None; conf_time = None
    start_j = max(0, i - 10)
    for k in range(i, start_j, -1):
        if k >= 2 and lows[k] < lows[k-2]:
            mid_high = highs[k-1]
            if mid_high - lows[k] >= 30.0:
                has_hh = True
                conf_price = mid_high
                conf_time = times[k-1]
                break

    if has_hh and unrealized >= 150.0:
        trail_angle = 60.0
    elif has_hh:
        trail_angle = 50.0
    else:
        trail_angle = 40.0

    trailing_slope = np.tan(np.deg2rad(trail_angle)) * (y_per_unit / x_per_unit)

    anchor_p = conf_price; anchor_t = conf_time
    if anchor_p is None:
        # Fallback: find swing high in last 15 bars
        anchor_p = 1e30; anchor_t = None; found = False
        for j in range(max(1, i-15), i):
            if j >= n-1: continue
            hi = highs[j]
            if hi - highs[j-1] >= SWING_MIN*0.3 and hi - highs[j+1] >= SWING_MIN*0.3:
                if hi < anchor_p:
                    anchor_p = hi; anchor_t = times[j]; found = True
        if not found:
            anchor_p = None

    stop_level = None; fired = False
    if anchor_p is not None and anchor_t is not None:
        t_diff = times[i] - anchor_t
        if t_diff > 0:
            stop_level = anchor_p - trailing_slope * t_diff
            if close > stop_level:
                fired = True

    anchor_str = f"{anchor_p:.0f}" if anchor_p and anchor_p < 1e29 else "None"
    stop_str   = f"{stop_level:.0f}" if stop_level else "None"
    print(f"{ts.strftime('%H:%M'):>6} {close:>7.0f} {unrealized:>+8.0f} {str(has_hh):>6} "
          f"{anchor_str:>8} {trail_angle:>7.0f} {stop_str:>9} {'FIRE' if fired else '':>6}")

    if fired:
        print(f"\n  >>> Trailing stop FIRED at {ts.strftime('%H:%M')}  close={close:.0f}  unrealized={unrealized:+.0f}")
        break
