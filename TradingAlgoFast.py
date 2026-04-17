"""TradingAlgoFast.py

Complete Numba-accelerated trading algo. Ports ALL computation to numpy/Numba
including trendline fitting, ray computation, and signal detection.

Produces identical results to TradingAlgo.py.
"""

import numpy as np
import pandas as pd
import pytz
from typing import Optional

try:
    from numba import jit
except ImportError:
    def jit(*args, **kwargs):
        def decorator(func):
            return func
        if len(args) == 1 and callable(args[0]):
            return args[0]
        return decorator

from TradingAlgo import AlgoConfig

_EST = pytz.timezone("US/Eastern")


# ---------------------------------------------------------------------------
# Trendline fitting (ported from TrendLineAutomation.py)
# ---------------------------------------------------------------------------

@jit(nopython=True, cache=True)
def _check_trend_line(support, pivot, slope, y):
    n = len(y)
    intercept = -slope * pivot + y[pivot]
    max_diff = -1e30
    min_diff = 1e30
    err = 0.0
    for i in range(n):
        val = slope * i + intercept
        diff = val - y[i]
        if diff > max_diff: max_diff = diff
        if diff < min_diff: min_diff = diff
        err += diff * diff
    if support and max_diff > 1e-5:
        return -1.0
    if not support and min_diff < -1e-5:
        return -1.0
    return err


@jit(nopython=True, cache=True)
def _optimize_slope(support, pivot, init_slope, y):
    y_range = y.max() - y.min()
    if y_range == 0:
        return init_slope, y[pivot]
    slope_unit = y_range / len(y)
    min_step = 0.0001
    curr_step = 1.0
    best_slope = init_slope
    best_err = _check_trend_line(support, pivot, init_slope, y)
    if best_err < 0.0:
        return best_slope, -best_slope * pivot + y[pivot]

    get_derivative = True
    derivative = 0.0
    while curr_step > min_step:
        if get_derivative:
            slope_change = best_slope + slope_unit * min_step
            test_err = _check_trend_line(support, pivot, slope_change, y)
            derivative = test_err - best_err
            if test_err < 0.0:
                slope_change = best_slope - slope_unit * min_step
                test_err = _check_trend_line(support, pivot, slope_change, y)
                derivative = best_err - test_err
            if test_err < 0.0:
                return best_slope, -best_slope * pivot + y[pivot]
            get_derivative = False

        if derivative > 0.0:
            test_slope = best_slope - slope_unit * curr_step
        else:
            test_slope = best_slope + slope_unit * curr_step

        test_err = _check_trend_line(support, pivot, test_slope, y)
        if test_err < 0 or test_err >= best_err:
            curr_step *= 0.5
        else:
            best_err = test_err
            best_slope = test_slope
            get_derivative = True

    return best_slope, -best_slope * pivot + y[pivot]


@jit(nopython=True, cache=True)
def _fit_trendlines(high, low, close):
    """Numba port of fit_trendlines_high_low."""
    n = len(close)
    x = np.arange(n, dtype=np.float64)

    # polyfit degree 1 (manual — numba doesn't support np.polyfit)
    x_mean = x.mean()
    c_mean = close.mean()
    num = 0.0
    den = 0.0
    for i in range(n):
        num += (x[i] - x_mean) * (close[i] - c_mean)
        den += (x[i] - x_mean) ** 2
    slope = num / den if den != 0 else 0.0
    intercept = c_mean - slope * x_mean

    # Find pivots
    upper_pivot = 0
    lower_pivot = 0
    max_diff = -1e30
    min_diff = 1e30
    for i in range(n):
        line_val = slope * i + intercept
        diff_h = high[i] - line_val
        diff_l = low[i] - line_val
        if diff_h > max_diff:
            max_diff = diff_h
            upper_pivot = i
        if diff_l < min_diff:
            min_diff = diff_l
            lower_pivot = i

    support_slope, support_intercept = _optimize_slope(True, lower_pivot, slope, low)
    resist_slope, resist_intercept = _optimize_slope(False, upper_pivot, slope, high)

    return support_slope, support_intercept, resist_slope, resist_intercept


# ---------------------------------------------------------------------------
# Full algo (Numba-compiled)
# ---------------------------------------------------------------------------

@jit(nopython=True, cache=True)
def _run_algo_numba(
    highs, lows, closes, times_num,
    orange_angle_deg, yellow_angle_deg,
    x_per_unit, y_per_unit,
    cutoff_idx, min_bars,
    steep_angle_threshold_deg, proximity_points,
):
    """Complete algo in Numba. Returns signal array."""
    n = len(closes)
    signals = np.zeros(n, dtype=np.int8)

    # Orange ray state
    orange_anchor_price = highs[0]
    orange_anchor_time  = times_num[0]
    orange_slope = -np.tan(np.deg2rad(orange_angle_deg)) * (y_per_unit / x_per_unit)

    # Yellow ray state
    yellow_anchor_price = lows[0]
    yellow_anchor_time  = times_num[0]
    yellow_slope = np.tan(np.deg2rad(yellow_angle_deg)) * (y_per_unit / x_per_unit)

    # Purple/blue state
    purple_anchor_time  = times_num[0]
    purple_anchor_price = highs[0]
    blue_anchor_time    = times_num[0]
    blue_anchor_price   = lows[0]

    # Ray value arrays (for output)
    orange_vals = np.zeros(n)
    yellow_vals = np.zeros(n)
    purple_vals = np.zeros(n)
    blue_vals   = np.zeros(n)

    # Pre-compute orange and yellow for all bars
    for i in range(n):
        if highs[i] > orange_anchor_price:
            orange_anchor_price = highs[i]
            orange_anchor_time  = times_num[i]
            orange_slope = -np.tan(np.deg2rad(orange_angle_deg)) * (y_per_unit / x_per_unit)
        orange_vals[i] = orange_anchor_price + orange_slope * (times_num[i] - orange_anchor_time)

        if lows[i] < yellow_anchor_price:
            yellow_anchor_price = lows[i]
            yellow_anchor_time  = times_num[i]
            yellow_slope = np.tan(np.deg2rad(yellow_angle_deg)) * (y_per_unit / x_per_unit)
        yellow_vals[i] = yellow_anchor_price + yellow_slope * (times_num[i] - yellow_anchor_time)

    # Compute purple/blue using trendline fitting incrementally
    for i in range(n):
        # Update anchors
        if highs[i] > purple_anchor_price:
            purple_anchor_price = highs[i]
            purple_anchor_time  = times_num[i]
        if lows[i] < blue_anchor_price:
            blue_anchor_price = lows[i]
            blue_anchor_time  = times_num[i]

        # Find anchor index
        p_start = 0
        b_start = 0
        for j in range(n):
            if times_num[j] >= purple_anchor_time:
                p_start = j; break
        for j in range(n):
            if times_num[j] >= blue_anchor_time:
                b_start = j; break

        if i - p_start >= 2:
            window_h = highs[p_start:i+1]
            window_l = lows[p_start:i+1]
            window_c = closes[p_start:i+1]
            s_slope, s_int, r_slope, r_int = _fit_trendlines(window_h, window_l, window_c)
            time_step = times_num[p_start+1] - times_num[p_start] if p_start+1 < n else 1.0
            if time_step == 0: time_step = 1.0
            r_slope_time = r_slope / time_step
            purple_vals[i] = r_int + r_slope * (i - p_start)
        else:
            purple_vals[i] = purple_anchor_price

        if i - b_start >= 2:
            window_h = highs[b_start:i+1]
            window_l = lows[b_start:i+1]
            window_c = closes[b_start:i+1]
            s_slope, s_int, r_slope, r_int = _fit_trendlines(window_h, window_l, window_c)
            blue_vals[i] = s_int + s_slope * (i - b_start)
        else:
            blue_vals[i] = blue_anchor_price

    # Signal detection
    position = 0  # 0=flat, 1=long, -1=short
    entry_idx = 0
    steep_thresh_rad = np.deg2rad(steep_angle_threshold_deg)

    for i in range(max(cutoff_idx, min_bars), n):
        prev_close  = closes[i-1]
        curr_close  = closes[i]
        prev_orange = orange_vals[i-1]
        prev_yellow = yellow_vals[i-1]
        prev_purple = purple_vals[i-1]
        prev_blue   = blue_vals[i-1]
        curr_orange = orange_vals[i]
        curr_yellow = yellow_vals[i]

        # BUY signals
        if position != 1:
            buy = False
            if prev_close <= prev_orange and curr_close > prev_orange:
                buy = True
            if not buy and prev_close <= prev_purple and curr_close > prev_purple:
                if abs(curr_close - curr_orange) > proximity_points:
                    buy = True
            if buy:
                signals[i] = 1
                position = 1
                entry_idx = i

        # SELL signals
        if position != -1 and signals[i] == 0:
            sell = False
            if prev_close >= prev_yellow and curr_close < prev_yellow:
                sell = True
            if not sell and prev_close >= prev_blue and curr_close < prev_blue:
                if abs(curr_close - curr_yellow) > proximity_points:
                    sell = True
            if sell:
                signals[i] = -1
                position = -1
                entry_idx = i

    return signals, orange_vals, yellow_vals, purple_vals, blue_vals


@jit(nopython=True, cache=True)
def _calc_pl(signals, closes, end_idx, min_reversal_bars):
    """P/L with reversal filter."""
    position = 0
    entry_price = 0.0
    entry_idx = 0
    total_pl = 0.0
    n_trades = 0
    n_winners = 0
    n_losers = 0

    for i in range(end_idx):
        sig = signals[i]
        if sig == 0: continue
        if position != 0 and sig != position:
            if min_reversal_bars > 0 and (i - entry_idx) < min_reversal_bars:
                continue
        if sig == 1:
            if position == -1:
                pl = entry_price - closes[i]
                total_pl += pl; n_trades += 1
                if pl > 0: n_winners += 1
                else: n_losers += 1
            position = 1; entry_price = closes[i]; entry_idx = i
        elif sig == -1:
            if position == 1:
                pl = closes[i] - entry_price
                total_pl += pl; n_trades += 1
                if pl > 0: n_winners += 1
                else: n_losers += 1
            position = -1; entry_price = closes[i]; entry_idx = i

    if position == 1:
        pl = closes[end_idx-1] - entry_price
        total_pl += pl; n_trades += 1
        if pl > 0: n_winners += 1
        else: n_losers += 1
    elif position == -1:
        pl = entry_price - closes[end_idx-1]
        total_pl += pl; n_trades += 1
        if pl > 0: n_winners += 1
        else: n_losers += 1

    return total_pl, n_trades, n_winners, n_losers


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_day_all_endtimes(
    df: pd.DataFrame,
    target_date: str,
    end_times: list,
    config: Optional[AlgoConfig] = None,
    min_reversal_minutes: int = 10,
) -> dict:
    """Run full Numba algo, slice by end times."""
    import matplotlib.dates as mdates

    cfg = config or AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                                proximity_points=15.0)

    est = pytz.timezone("US/Eastern")
    data = df.copy()
    try:
        if data.index.tz is None:
            data.index = pd.to_datetime(data.index).tz_localize(est)
        else:
            data.index = pd.to_datetime(data.index).tz_convert(est)
    except: pass

    highs  = data["High"].values.astype(np.float64)
    lows   = data["Low"].values.astype(np.float64)
    closes = data["Close"].values.astype(np.float64)
    times_num = np.array([mdates.date2num(t) for t in data.index])

    # Aspect ratio
    x_range = 75 / (24 * 60)
    y_range = highs.max() + 20 - (lows.min() - 20)
    ax_w_in = 16.0 * (0.85 - 0.125)
    ax_h_in = 9.0 * (0.88 - 0.11)
    x_per_unit = x_range / ax_w_in
    y_per_unit = y_range / ax_h_in

    # Warmup cutoff
    cutoff_time = data.index[0] + pd.Timedelta(minutes=cfg.warmup_minutes or 12)
    cutoff_idx = 0
    for i, t in enumerate(data.index):
        if t >= cutoff_time:
            cutoff_idx = i; break

    # Run Numba algo
    signals, _, _, _, _ = _run_algo_numba(
        highs, lows, closes, times_num,
        cfg.orange_angle, cfg.yellow_angle,
        x_per_unit, y_per_unit,
        cutoff_idx, 3,
        cfg.steep_angle_threshold, cfg.proximity_points,
    )

    # Slice by end times
    results = {}
    for end_time in end_times:
        try:
            end_ts = pd.Timestamp(f"{target_date} {end_time}", tz=est)
            mask = data.index <= end_ts
            end_idx = int(mask.sum())
            if end_idx < 10: continue

            total_pl, n_trades, n_winners, n_losers = _calc_pl(
                signals, closes, end_idx, min_reversal_minutes)

            if n_trades > 0:
                results[end_time] = {
                    "trades": n_trades, "pl": float(total_pl),
                    "winners": n_winners, "losers": n_losers,
                }
        except: continue

    return results
