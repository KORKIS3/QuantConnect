"""Sweep swing anchor threshold to find best purple/blue re-anchor logic."""
import os, pandas as pd, pytz, numpy as np
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig, _compute_rays_nb, _fit_trendlines_nb, _display_angle_from_slope
import matplotlib.dates as mdates

_EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1000")
SIM_CSV = os.path.join("SIM", "sim_trade_analysis.csv")
sim = pd.read_csv(SIM_CSV)

sim_total = sum(int(str(r).replace("+","").replace(",","")) for r in sim["total_pl_pts"])

def run_with_anchor(swing_thresh, min_distance):
    """Run all sim days with custom anchor logic, return total algo pts."""
    total = 0; days = 0
    for _, row in sim.iterrows():
        date = str(row["date"])
        fname = os.path.join(DATA_ROOT, f"CBOT_MINI_YM1_{date}.csv")
        if not os.path.exists(fname): continue
        df = pd.read_csv(fname, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)

        highs  = df["High"].values.astype(np.float64)
        lows   = df["Low"].values.astype(np.float64)
        closes = df["Close"].values.astype(np.float64)
        times  = np.array([mdates.date2num(t) for t in df.index])
        n = len(highs)

        _y_range = highs.max() + 20.0 - (lows.min() - 20.0)
        x_per_unit = (75/(24*60)) / (16.0*(0.85-0.125))
        y_per_unit = _y_range / (9.0*(0.88-0.11))
        orange_slope = -np.tan(np.deg2rad(2.5)) * (y_per_unit / x_per_unit)
        yellow_slope =  np.tan(np.deg2rad(2.5)) * (y_per_unit / x_per_unit)

        # Custom purple/blue with swing re-anchor
        purple_vals = np.full(n, highs[0]); blue_vals = np.full(n, lows[0])
        purple_slopes = np.zeros(n); blue_slopes = np.zeros(n)
        purple_start_prices = np.full(n, highs[0]); blue_start_prices = np.full(n, lows[0])
        p_anchor_p = highs[0]; p_anchor_idx = 0
        b_anchor_p = lows[0];  b_anchor_idx = 0

        for i in range(n):
            # Re-anchor on swing high if it's far enough from current anchor
            if i >= 2:
                j = i - 1
                if (highs[j] - highs[j-1] >= swing_thresh and
                    highs[j] - highs[i]   >= swing_thresh and
                    abs(highs[j] - p_anchor_p) >= min_distance):
                    p_anchor_p = highs[j]; p_anchor_idx = j

                if (lows[j-1] - lows[j] >= swing_thresh and
                    lows[i]   - lows[j] >= swing_thresh and
                    abs(lows[j] - b_anchor_p) >= min_distance):
                    b_anchor_p = lows[j]; b_anchor_idx = j

            # Also keep original: move to new absolute high/low
            if highs[i] > p_anchor_p: p_anchor_p = highs[i]; p_anchor_idx = i
            if lows[i]  < b_anchor_p: b_anchor_p = lows[i];  b_anchor_idx = i

            pw_start = p_anchor_idx; bw_start = b_anchor_idx
            pw_len = i + 1 - pw_start; bw_len = i + 1 - bw_start

            if pw_len >= 2 and bw_len >= 2:
                pw_h = highs[pw_start:i+1]; pw_l = lows[pw_start:i+1]; pw_c = closes[pw_start:i+1]
                _, _, r_s, r_i = _fit_trendlines_nb(pw_h, pw_l, pw_c)
                ts = times[pw_start+1] - times[pw_start]
                if ts == 0: ts = 1.0
                purple_slopes[i] = r_s / ts; purple_start_prices[i] = r_i
                purple_vals[i] = r_i + (r_s/ts) * (times[i] - times[pw_start])

                bw_h = highs[bw_start:i+1]; bw_l = lows[bw_start:i+1]; bw_c = closes[bw_start:i+1]
                s_s, s_i, _, _ = _fit_trendlines_nb(bw_h, bw_l, bw_c)
                ts = times[bw_start+1] - times[bw_start]
                if ts == 0: ts = 1.0
                blue_slopes[i] = s_s / ts; blue_start_prices[i] = s_i
                blue_vals[i] = s_i + (s_s/ts) * (times[i] - times[bw_start])
            elif i > 0:
                purple_slopes[i] = purple_slopes[i-1]; purple_start_prices[i] = purple_start_prices[i-1]
                purple_vals[i] = purple_start_prices[i-1] + purple_slopes[i-1] * (times[i] - times[p_anchor_idx])
                blue_slopes[i] = blue_slopes[i-1]; blue_start_prices[i] = blue_start_prices[i-1]
                blue_vals[i] = blue_start_prices[i-1] + blue_slopes[i-1] * (times[i] - times[b_anchor_idx])

        # Now run signals using these custom rays via the standard algo
        # (inject into result by running algo and overriding — simplest: just run algo normally
        # since we can't easily inject custom rays without refactoring)
        # Instead, just run the standard algo for now and compare angles
        cfg = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                         proximity_points=15.0, min_reversal_minutes=10)
        try:
            result = run_trading_algo_fast(df, date, "09:30", "10:30", config=cfg)
            total += float(result["pl"].iloc[-1]); days += 1
        except: pass
    return total, days

# First establish what angles we get with different thresholds
print("Checking angles on 02/03 with different swing thresholds:\n")
date = "2026-02-03"
df = pd.read_csv(os.path.join(DATA_ROOT, f"CBOT_MINI_YM1_{date}.csv"), index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
highs  = df["High"].values.astype(np.float64)
lows   = df["Low"].values.astype(np.float64)
closes = df["Close"].values.astype(np.float64)
times  = np.array([mdates.date2num(t) for t in df.index])
_y_range = highs.max() + 20.0 - (lows.min() - 20.0)
x_per_unit = (75/(24*60)) / (16.0*(0.85-0.125))
y_per_unit = _y_range / (9.0*(0.88-0.11))

for swing_t in [20, 30, 40, 50, 75, 100]:
    for min_d in [50, 100, 150, 200]:
        p_anchor_p = highs[0]; p_anchor_idx = 0
        b_anchor_p = lows[0];  b_anchor_idx = 0
        p_slopes = np.zeros(len(highs)); b_slopes = np.zeros(len(highs))

        for i in range(len(highs)):
            if i >= 2:
                j = i - 1
                if (highs[j] - highs[j-1] >= swing_t and highs[j] - highs[i] >= swing_t and
                    abs(highs[j] - p_anchor_p) >= min_d):
                    p_anchor_p = highs[j]; p_anchor_idx = j
                if (lows[j-1] - lows[j] >= swing_t and lows[i] - lows[j] >= swing_t and
                    abs(lows[j] - b_anchor_p) >= min_d):
                    b_anchor_p = lows[j]; b_anchor_idx = j
            if highs[i] > p_anchor_p: p_anchor_p = highs[i]; p_anchor_idx = i
            if lows[i]  < b_anchor_p: b_anchor_p = lows[i];  b_anchor_idx = i

            pw = i + 1 - p_anchor_idx; bw = i + 1 - b_anchor_idx
            if pw >= 2 and bw >= 2:
                _, _, r_s, r_i = _fit_trendlines_nb(highs[p_anchor_idx:i+1], lows[p_anchor_idx:i+1], closes[p_anchor_idx:i+1])
                ts = times[p_anchor_idx+1] - times[p_anchor_idx]
                if ts == 0: ts = 1.0
                p_slopes[i] = r_s / ts
                s_s, _, _, _ = _fit_trendlines_nb(highs[b_anchor_idx:i+1], lows[b_anchor_idx:i+1], closes[b_anchor_idx:i+1])
                ts = times[b_anchor_idx+1] - times[b_anchor_idx]
                if ts == 0: ts = 1.0
                b_slopes[i] = s_s / ts

        # Angle at bar 12 (warmup) and bar 30 (mid session)
        pa12 = _display_angle_from_slope(p_slopes[12], x_per_unit, y_per_unit)
        ba12 = _display_angle_from_slope(b_slopes[12], x_per_unit, y_per_unit)
        pa30 = _display_angle_from_slope(p_slopes[30], x_per_unit, y_per_unit)
        ba30 = _display_angle_from_slope(b_slopes[30], x_per_unit, y_per_unit)
        print(f"swing={swing_t:3d} min_dist={min_d:3d}  purple@12={pa12:.0f}° @30={pa30:.0f}°  blue@12={ba12:.0f}° @30={ba30:.0f}°")
    print()
