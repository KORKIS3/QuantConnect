import pandas as pd, pytz, os, numpy as np
import matplotlib.dates as mdates
est = pytz.timezone("US/Eastern")
data_root = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1130")
df = pd.read_csv(os.path.join(data_root, "CBOT_MINI_YM1_2026-03-25.csv"), index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)
highs = df["High"].values.astype(np.float64)
times_num = np.array([mdates.date2num(t) for t in df.index])
n = len(highs)
SWING_THRESHOLD = 50.0

mag_anchor_price = None; mag_anchor_idx = -1; mag_slope_frozen = False; mag_slope = 0.0
magenta_vals = np.full(n, np.nan)

for i in range(n):
    if i >= 2:
        for j in range(1, i):
            if j >= n - 1: continue
            h = highs[j]; h_prev = highs[j-1]; h_next = highs[j+1]
            if h - h_prev >= SWING_THRESHOLD and h - h_next >= SWING_THRESHOLD:
                if mag_anchor_price is None or h > mag_anchor_price:
                    if mag_anchor_idx != j:
                        mag_anchor_price = h; mag_anchor_idx = j; mag_slope_frozen = False

    # Build magenta ray
    if mag_anchor_idx >= 0 and not mag_slope_frozen:
        candidates_h = -1e9; candidates_idx = -1
        for j in range(mag_anchor_idx + 1, i + 1):
            if highs[j] < mag_anchor_price and highs[j] > candidates_h:
                candidates_h = highs[j]; candidates_idx = j
        if candidates_idx >= 0:
            dt = times_num[candidates_idx] - times_num[mag_anchor_idx]
            if dt != 0:
                mag_slope = (candidates_h - mag_anchor_price) / dt
                mag_slope_frozen = True
                if i >= 55 and i <= 58:
                    print(f"  SLOPE FROZEN at i={i}: anchor={mag_anchor_idx} candidate={candidates_idx} slope={mag_slope:.1f}")

    if mag_slope_frozen and mag_anchor_idx >= 0:
        magenta_vals[i] = mag_anchor_price + mag_slope * (times_num[i] - times_num[mag_anchor_idx])

    if i >= 55 and i <= 60:
        mv = magenta_vals[i]
        mv_str = f"{mv:.1f}" if not np.isnan(mv) else "NaN"
        print(f"i={i}: anchor={mag_anchor_idx} frozen={mag_slope_frozen} magenta={mv_str}")
