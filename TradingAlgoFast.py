"""TradingAlgoFast.py

Exact port of TradingAlgo.run_trading_algo using numpy arrays instead of
pandas DataFrames for the inner loops. Produces IDENTICAL signals.

The speedup comes from eliminating ~600K pandas __getitem__ calls per day
and using Numba-compiled trendline fitting.
"""

import numpy as np
import pandas as pd
import pytz
import matplotlib.dates as mdates
from typing import Optional, Dict

try:
    from numba import jit
except ImportError:
    def jit(*args, **kwargs):
        def decorator(func): return func
        if len(args) == 1 and callable(args[0]): return args[0]
        return decorator

_EST = pytz.timezone("US/Eastern")


# ---------------------------------------------------------------------------
# AlgoConfig — single source of truth (moved here from TradingAlgo.py)
# ---------------------------------------------------------------------------

from dataclasses import dataclass

@dataclass
class AlgoConfig:
    """Parameters that define a trading algorithm scenario."""
    orange_angle: float = 2.5
    yellow_angle: float = 2.5
    purple_angle: float = 45.0
    blue_angle: float = 45.0
    steep_angle_threshold: float = 45.0
    proximity_points: float = 50.0
    warmup_minutes: Optional[int] = None
    min_reversal_minutes: int = 10
    max_loss_per_trade: float = 0.0
    confirmation_bars: int = 0
    spike_profit_pts: float = 100.0
    spike_profit_bars: int = 5
    wm_shield_distance: float = 12.0
    wm_tolerance: float = 12.0
    wm_min_touches: int = 4
    wm_min_span: float = 15.0
    wm_lookback: int = 30
    partial_tp_pts: float = 50.0
    num_contracts: int = 2
    first_entry_steep_only: bool = False  # first trade must be purple/blue cross, not orange/yellow
    min_entry_angle: float = 0.0          # wait until purple or blue exceeds this angle before first entry


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _display_angle_from_slope(slope: float, x_per_unit: float = 1.0, y_per_unit: float = 1.0) -> float:
    """Return the visual angle in degrees of a ray given its slope."""
    return float(abs(np.rad2deg(np.arctan(abs(slope) * x_per_unit / y_per_unit))))


def _build_signals_frame(
    data: pd.DataFrame,
    buy_signals: Dict,
    sell_signals: Dict,
    trading_halted: bool,
    halt_time,
    liquidation_timestamps: Optional[set] = None,
) -> pd.DataFrame:
    """Construct a per-minute DataFrame with signals and cumulative P/L."""
    df = data.copy()
    liq_ts = liquidation_timestamps or set()

    df["signal"] = ""
    df["buy_price"] = pd.NA
    df["sell_price"] = pd.NA
    df["is_liquidation"] = False

    for ts, price in buy_signals.items():
        if ts in df.index:
            df.at[ts, "signal"] = "BUY"
            df.at[ts, "buy_price"] = float(price)
            if ts in liq_ts:
                df.at[ts, "is_liquidation"] = True

    for ts, price in sell_signals.items():
        if ts in df.index:
            df.at[ts, "signal"] = "SELL"
            df.at[ts, "sell_price"] = float(price)
            if ts in liq_ts:
                df.at[ts, "is_liquidation"] = True

    position = "flat"
    entry_price: Optional[float] = None
    cumulative_realized_pl: float = 0.0
    positions = []
    pls = []

    for ts in df.index:
        if trading_halted and halt_time is not None and ts > halt_time:
            positions.append("flat")
            pls.append(cumulative_realized_pl)
            continue

        is_buy  = ts in buy_signals
        is_sell = ts in sell_signals
        is_liq  = ts in liq_ts

        if is_buy:
            buy_price = float(buy_signals[ts])
            if position == "short" and entry_price is not None:
                cumulative_realized_pl += entry_price - buy_price
            position   = "flat" if is_liq else "long"
            entry_price = None  if is_liq else buy_price

        if is_sell:
            sell_price = float(sell_signals[ts])
            if position == "long" and entry_price is not None:
                cumulative_realized_pl += sell_price - entry_price
            position   = "flat"  if is_liq else "short"
            entry_price = None   if is_liq else sell_price

        current_close = float(df.loc[ts, "Close"])
        unrealized = 0.0
        if position == "long"  and entry_price is not None:
            unrealized = current_close - entry_price
        elif position == "short" and entry_price is not None:
            unrealized = entry_price - current_close

        positions.append(position)
        pls.append(cumulative_realized_pl + unrealized)

    df["position"] = positions
    df["pl"] = pls
    return df


def _find_wm_clusters(values, times, tolerance=12.0, min_touches=4, min_span_minutes=15.0):
    """Find price clusters where multiple bar lows/highs land within tolerance pts."""
    if len(values) < min_touches:
        return []
    indexed = sorted(zip(values, times), key=lambda x: x[0])
    clusters = []
    used = set()
    for i in range(len(indexed)):
        if i in used:
            continue
        base = indexed[i][0]
        group = [(indexed[i][0], indexed[i][1])]
        used.add(i)
        for j in range(i + 1, len(indexed)):
            if j in used:
                continue
            if abs(indexed[j][0] - base) <= tolerance:
                group.append((indexed[j][0], indexed[j][1]))
                used.add(j)
            elif indexed[j][0] - base > tolerance:
                break
        if len(group) >= min_touches:
            touch_times = sorted([g[1] for g in group])
            span = (touch_times[-1] - touch_times[0]).total_seconds() / 60
            if span >= min_span_minutes:
                clusters.append((float(np.mean([g[0] for g in group])), len(group)))
    return clusters


# --- Numba-compiled trendline fitting (exact port of TrendLineAutomation.py) ---

@jit(nopython=True, cache=True)
def _check_trend_line_nb(support, pivot, slope, y):
    n = len(y)
    intercept = -slope * pivot + y[pivot]
    max_diff = -1e30; min_diff = 1e30; err = 0.0
    for i in range(n):
        val = slope * i + intercept
        diff = val - y[i]
        if diff > max_diff: max_diff = diff
        if diff < min_diff: min_diff = diff
        err += diff * diff
    if support and max_diff > 1e-5: return -1.0
    if not support and min_diff < -1e-5: return -1.0
    return err

@jit(nopython=True, cache=True)
def _optimize_slope_nb(support, pivot, init_slope, y):
    y_max = y[0]; y_min = y[0]
    for i in range(len(y)):
        if y[i] > y_max: y_max = y[i]
        if y[i] < y_min: y_min = y[i]
    if y_max == y_min: return init_slope, y[pivot]
    slope_unit = (y_max - y_min) / len(y)
    min_step = 0.0001; curr_step = 1.0
    best_slope = init_slope
    best_err = _check_trend_line_nb(support, pivot, init_slope, y)
    if best_err < 0.0: return best_slope, -best_slope * pivot + y[pivot]
    get_derivative = True; derivative = 0.0
    while curr_step > min_step:
        if get_derivative:
            slope_change = best_slope + slope_unit * min_step
            test_err = _check_trend_line_nb(support, pivot, slope_change, y)
            derivative = test_err - best_err
            if test_err < 0.0:
                slope_change = best_slope - slope_unit * min_step
                test_err = _check_trend_line_nb(support, pivot, slope_change, y)
                derivative = best_err - test_err
            if test_err < 0.0: return best_slope, -best_slope * pivot + y[pivot]
            get_derivative = False
        if derivative > 0.0: test_slope = best_slope - slope_unit * curr_step
        else: test_slope = best_slope + slope_unit * curr_step
        test_err = _check_trend_line_nb(support, pivot, test_slope, y)
        if test_err < 0 or test_err >= best_err: curr_step *= 0.5
        else: best_err = test_err; best_slope = test_slope; get_derivative = True
    return best_slope, -best_slope * pivot + y[pivot]

@jit(nopython=True, cache=True)
def _fit_trendlines_nb(high, low, close):
    """Numba port of fit_trendlines_high_low — exact same logic."""
    n = len(close)
    # Manual polyfit degree 1
    x_mean = 0.0; c_mean = 0.0
    for i in range(n): x_mean += i; c_mean += close[i]
    x_mean /= n; c_mean /= n
    num = 0.0; den = 0.0
    for i in range(n):
        num += (i - x_mean) * (close[i] - c_mean)
        den += (i - x_mean) ** 2
    slope = num / den if den != 0 else 0.0
    intercept = c_mean - slope * x_mean
    # Find pivots
    upper_pivot = 0; lower_pivot = 0; max_diff = -1e30; min_diff = 1e30
    for i in range(n):
        line_val = slope * i + intercept
        if high[i] - line_val > max_diff: max_diff = high[i] - line_val; upper_pivot = i
        if low[i] - line_val < min_diff: min_diff = low[i] - line_val; lower_pivot = i
    s_slope, s_int = _optimize_slope_nb(True, lower_pivot, slope, low)
    r_slope, r_int = _optimize_slope_nb(False, upper_pivot, slope, high)
    return s_slope, s_int, r_slope, r_int


# ---------------------------------------------------------------------------
# Numba-compiled ray computation — all 6 rays in one pass
# ---------------------------------------------------------------------------

@jit(nopython=True, cache=True)
def _compute_rays_nb(
    n, highs_arr, lows_arr, closes_arr, times_num,
    orange_slope_val, yellow_slope_val,
):
    """Compute all ray values in a single Numba-compiled pass.
    Returns: orange_vals, yellow_vals, purple_vals, blue_vals,
             purple_slopes, blue_slopes, purple_start_prices, blue_start_prices,
             magenta_vals, magenta_slopes, lime_vals, lime_slopes_arr,
             p_anchor_p, p_anchor_idx, b_anchor_p, b_anchor_idx
    """
    # --- Orange ray ---
    orange_vals = np.zeros(n)
    o_anchor_p = highs_arr[0]; o_anchor_t = times_num[0]
    for i in range(n):
        if highs_arr[i] > o_anchor_p:
            o_anchor_p = highs_arr[i]; o_anchor_t = times_num[i]
        orange_vals[i] = o_anchor_p + orange_slope_val * (times_num[i] - o_anchor_t)

    # --- Yellow ray ---
    yellow_vals = np.zeros(n)
    y_anchor_p = lows_arr[0]; y_anchor_t = times_num[0]
    for i in range(n):
        if lows_arr[i] < y_anchor_p:
            y_anchor_p = lows_arr[i]; y_anchor_t = times_num[i]
        yellow_vals[i] = y_anchor_p + yellow_slope_val * (times_num[i] - y_anchor_t)

    # --- Purple/blue rays ---
    # Purple anchors at session high, then re-anchors at each subsequent LOWER swing high.
    # Blue anchors at session low, then re-anchors at each subsequent HIGHER swing low.
    # This keeps lines steep by shortening the window as the session progresses.
    SWING_ANCHOR_THRESHOLD = 30.0  # min pts to qualify as a swing high/low
    purple_vals         = np.full(n, highs_arr[0])
    blue_vals           = np.full(n, lows_arr[0])
    purple_slopes       = np.zeros(n)
    blue_slopes         = np.zeros(n)
    purple_start_prices = np.full(n, highs_arr[0])
    blue_start_prices   = np.full(n, lows_arr[0])

    # Purple: start at session high, move forward to each lower swing high
    p_session_high = highs_arr[0]; p_session_high_idx = 0
    p_anchor_idx = 0
    # Blue: start at session low, move forward to each higher swing low
    b_session_low = lows_arr[0]; b_session_low_idx = 0
    b_anchor_idx = 0

    for i in range(n):
        # Track absolute session high/low
        if highs_arr[i] > p_session_high:
            p_session_high = highs_arr[i]; p_session_high_idx = i
            p_anchor_idx = i  # new session high becomes new anchor
        if lows_arr[i] < b_session_low:
            b_session_low = lows_arr[i]; b_session_low_idx = i
            b_anchor_idx = i  # new session low becomes new anchor

        # Re-anchor purple at most recent swing high that is LOWER than current anchor
        # (confirmed 1 bar later — bar j is a swing high if higher than both neighbours)
        if i >= 2:
            j = i - 1
            h_j = highs_arr[j]
            if (h_j - highs_arr[j-1] >= SWING_ANCHOR_THRESHOLD and
                h_j - highs_arr[i]   >= SWING_ANCHOR_THRESHOLD and
                j > p_anchor_idx and
                h_j < highs_arr[p_anchor_idx]):
                # Lower swing high — move anchor forward
                p_anchor_idx = j

            # Re-anchor blue at most recent swing low that is HIGHER than current anchor
            l_j = lows_arr[j]
            if (lows_arr[j-1] - l_j >= SWING_ANCHOR_THRESHOLD and
                lows_arr[i]   - l_j >= SWING_ANCHOR_THRESHOLD and
                j > b_anchor_idx and
                l_j > lows_arr[b_anchor_idx]):
                # Higher swing low — move anchor forward
                b_anchor_idx = j

        pw_start = p_anchor_idx; bw_start = b_anchor_idx
        pw_len = i + 1 - pw_start; bw_len = i + 1 - bw_start

        if pw_len >= 2 and bw_len >= 2:
            pw_h = highs_arr[pw_start:i+1]; pw_l = lows_arr[pw_start:i+1]; pw_c = closes_arr[pw_start:i+1]
            _, _, r_slope_nb, r_int_nb = _fit_trendlines_nb(pw_h, pw_l, pw_c)
            time_step = times_num[pw_start+1] - times_num[pw_start]
            if time_step == 0.0: time_step = 1.0
            r_slope_time = r_slope_nb / time_step
            purple_start_prices[i] = r_int_nb
            purple_slopes[i]       = r_slope_time
            purple_vals[i] = r_int_nb + r_slope_time * (times_num[i] - times_num[pw_start])

            bw_h = highs_arr[bw_start:i+1]; bw_l = lows_arr[bw_start:i+1]; bw_c = closes_arr[bw_start:i+1]
            s_slope_nb2, s_int_nb2, _, _ = _fit_trendlines_nb(bw_h, bw_l, bw_c)
            time_step = times_num[bw_start+1] - times_num[bw_start]
            if time_step == 0.0: time_step = 1.0
            s_slope_time = s_slope_nb2 / time_step
            blue_start_prices[i] = s_int_nb2
            blue_slopes[i]       = s_slope_time
            blue_vals[i] = s_int_nb2 + s_slope_time * (times_num[i] - times_num[bw_start])
        else:
            if i > 0:
                purple_slopes[i]       = purple_slopes[i-1]
                purple_start_prices[i] = purple_start_prices[i-1]
                purple_vals[i] = purple_start_prices[i-1] + purple_slopes[i-1] * (times_num[i] - times_num[pw_start])
                blue_slopes[i]       = blue_slopes[i-1]
                blue_start_prices[i] = blue_start_prices[i-1]
                blue_vals[i] = blue_start_prices[i-1] + blue_slopes[i-1] * (times_num[i] - times_num[bw_start])

        # Keep p_anchor_p/b_anchor_p in sync for compatibility
        p_anchor_p = highs_arr[p_anchor_idx]
        b_anchor_p = lows_arr[b_anchor_idx]

    # --- Magenta/lime swing rays ---
    SWING_THRESHOLD = 50.0
    magenta_vals    = np.full(n, np.nan)
    lime_vals       = np.full(n, np.nan)
    magenta_slopes  = np.full(n, np.nan)
    lime_slopes_arr = np.full(n, np.nan)

    mag_anchor_price = -1e30; mag_anchor_idx = -1; mag_slope_frozen = False; mag_slope = 0.0
    lime_anchor_price = 1e30; lime_anchor_idx = -1; lime_slope_frozen = False; lime_slope = 0.0
    _mag_best_h = -1e30; _mag_best_idx = -1
    _lime_best_l = 1e30; _lime_best_idx = -1
    mag_has_anchor = False; lime_has_anchor = False

    for i in range(n):
        if i >= 2:
            j = i - 1
            if j < n - 1:
                h = highs_arr[j]; h_prev = highs_arr[j-1]; h_next = highs_arr[j+1]
                if h - h_prev >= SWING_THRESHOLD and h - h_next >= SWING_THRESHOLD:
                    if not mag_has_anchor or h > mag_anchor_price:
                        mag_anchor_price = h; mag_anchor_idx = j; mag_slope_frozen = False
                        _mag_best_h = -1e30; _mag_best_idx = -1; mag_has_anchor = True

                lo = lows_arr[j]; lo_prev = lows_arr[j-1]; lo_next = lows_arr[j+1]
                if lo_prev - lo >= SWING_THRESHOLD and lo_next - lo >= SWING_THRESHOLD:
                    if not lime_has_anchor or lo < lime_anchor_price:
                        lime_anchor_price = lo; lime_anchor_idx = j; lime_slope_frozen = False
                        _lime_best_l = 1e30; _lime_best_idx = -1; lime_has_anchor = True

        if mag_has_anchor and mag_anchor_idx >= 0 and not mag_slope_frozen:
            if i > mag_anchor_idx and highs_arr[i] < mag_anchor_price and highs_arr[i] > _mag_best_h:
                _mag_best_h = highs_arr[i]; _mag_best_idx = i
            if _mag_best_idx >= 0:
                dt = times_num[_mag_best_idx] - times_num[mag_anchor_idx]
                if dt != 0.0:
                    mag_slope = (_mag_best_h - mag_anchor_price) / dt
                    mag_slope_frozen = True

        if mag_slope_frozen and mag_anchor_idx >= 0:
            magenta_vals[i]   = mag_anchor_price + mag_slope * (times_num[i] - times_num[mag_anchor_idx])
            magenta_slopes[i] = mag_slope

        if lime_has_anchor and lime_anchor_idx >= 0 and not lime_slope_frozen:
            if i > lime_anchor_idx and lows_arr[i] > lime_anchor_price and lows_arr[i] < _lime_best_l:
                _lime_best_l = lows_arr[i]; _lime_best_idx = i
            if _lime_best_idx >= 0:
                dt = times_num[_lime_best_idx] - times_num[lime_anchor_idx]
                if dt != 0.0:
                    lime_slope = (_lime_best_l - lime_anchor_price) / dt
                    lime_slope_frozen = True

        if lime_slope_frozen and lime_anchor_idx >= 0:
            lime_vals[i]       = lime_anchor_price + lime_slope * (times_num[i] - times_num[lime_anchor_idx])
            lime_slopes_arr[i] = lime_slope

    return (orange_vals, yellow_vals, purple_vals, blue_vals,
            purple_slopes, blue_slopes, purple_start_prices, blue_start_prices,
            magenta_vals, magenta_slopes, lime_vals, lime_slopes_arr,
            p_anchor_p, p_anchor_idx, b_anchor_p, b_anchor_idx)


# ---------------------------------------------------------------------------
# Numba-compiled signal detection loop
# ---------------------------------------------------------------------------
# Position encoding: 0=flat, 1=long, 2=short

@jit(nopython=True, cache=True)
def _run_signals_nb(
    n, cutoff_idx,
    closes_arr, highs_arr, lows_arr, times_num,
    orange_vals, yellow_vals, purple_vals, blue_vals,
    orange_slope_val, yellow_slope_val,
    purple_slopes, blue_slopes,
    magenta_vals, magenta_slopes,
    lime_vals, lime_slopes_arr,
    x_per_unit, y_per_unit,
    steep_angle_threshold, proximity_points,
    min_reversal_minutes, confirmation_bars,
    first_entry_steep_only,
    min_entry_angle,
):
    """Pure numpy signal detection — returns parallel arrays of signals."""
    sig_type  = np.zeros(n, dtype=np.int8)
    sig_price = np.zeros(n, dtype=np.float64)
    sig_liq   = np.zeros(n, dtype=np.bool_)

    pos = 0  # 0=flat, 1=long, 2=short
    entry_price = 0.0
    entry_time_num = 0.0
    session_pl = 0.0
    pending_buy  = False
    pending_sell = False
    pending_ray_val = 0.0
    min_per_unit = 1.0 / (24.0 * 60.0)
    first_trade_done = False  # tracks if first trade of session has fired

    for i in range(max(cutoff_idx, 3), n):
        close      = closes_arr[i]
        prev_close = closes_arr[i - 1]
        prev_orange = orange_vals[i - 1]
        prev_yellow = yellow_vals[i - 1]
        prev_purple = purple_vals[i - 1]
        prev_blue   = blue_vals[i - 1]
        _dt = times_num[i] - times_num[i - 1]
        curr_orange = prev_orange + orange_slope_val * _dt
        curr_yellow = prev_yellow + yellow_slope_val * _dt
        prev_purple_slope = purple_slopes[i - 1]
        prev_blue_slope   = blue_slopes[i - 1]
        liquidated = False
        is_last = (i == n - 1)

        # --- Trailing stop v3 ---
        if pos != 0 and i >= 5:
            unrealized = (close - entry_price) if pos == 1 else (entry_price - close)
            if unrealized >= 75.0:
                has_hh = False; conf_price = 0.0; conf_time = 0.0
                start_j = max(0, i - 10)
                if pos == 1 and i >= 4:
                    for k in range(i, start_j, -1):
                        if k >= 2 and highs_arr[k] > highs_arr[k - 2]:
                            mid_low = lows_arr[k - 1]
                            if highs_arr[k] - mid_low >= 30.0:
                                has_hh = True; conf_price = mid_low; conf_time = times_num[k - 1]; break
                elif pos == 2 and i >= 4:
                    for k in range(i, start_j, -1):
                        if k >= 2 and lows_arr[k] < lows_arr[k - 2]:
                            mid_high = highs_arr[k - 1]
                            if mid_high - lows_arr[k] >= 30.0:
                                has_hh = True; conf_price = mid_high; conf_time = times_num[k - 1]; break

                trail_angle = 60.0 if (has_hh and unrealized >= 150.0) else (50.0 if has_hh else 40.0)
                trailing_slope = np.tan(np.deg2rad(trail_angle)) * (y_per_unit / x_per_unit)

                anchor_p = conf_price; anchor_t = conf_time
                if not has_hh:
                    anchor_p = -1e30 if pos == 1 else 1e30; anchor_t = 0.0; found = False
                    for j in range(max(1, i - 15), i):
                        if j >= n - 1: continue
                        if pos == 1:
                            lo = lows_arr[j]
                            if lows_arr[j-1] - lo >= 15.0 and lows_arr[j+1] - lo >= 15.0:
                                if lo > anchor_p: anchor_p = lo; anchor_t = times_num[j]; found = True
                        else:
                            hi = highs_arr[j]
                            if hi - highs_arr[j-1] >= 15.0 and hi - highs_arr[j+1] >= 15.0:
                                if hi < anchor_p: anchor_p = hi; anchor_t = times_num[j]; found = True
                    if not found: anchor_p = -1e30

                if anchor_p > -1e29 and anchor_t > 0.0:
                    t_diff = times_num[i] - anchor_t
                    if t_diff > 0.0:
                        if pos == 1:
                            if close < anchor_p + trailing_slope * t_diff:
                                session_pl += close - entry_price
                                sig_type[i] = 2; sig_price[i] = close; sig_liq[i] = True
                                pos = 0; entry_price = 0.0; entry_time_num = 0.0; liquidated = True
                        else:
                            if close > anchor_p - trailing_slope * t_diff:
                                session_pl += entry_price - close
                                sig_type[i] = 1; sig_price[i] = close; sig_liq[i] = True
                                pos = 0; entry_price = 0.0; entry_time_num = 0.0; liquidated = True

        # Reversal guard
        mins_since = (times_num[i] - entry_time_num) / min_per_unit if entry_time_num > 0.0 else 9999.0
        orange_cross_buy  = prev_close <= prev_orange and close > prev_orange
        yellow_cross_sell = prev_close >= prev_yellow and close < prev_yellow
        safety_override   = (pos == 2 and orange_cross_buy) or (pos == 1 and yellow_cross_sell)
        reversal_blocked  = min_reversal_minutes > 0 and mins_since < min_reversal_minutes and not safety_override

        # Angle readiness — for first entry, require purple or blue to be steep enough
        if min_entry_angle > 0.0 and not first_trade_done:
            _pa = abs(np.rad2deg(np.arctan(abs(prev_purple_slope) * x_per_unit / y_per_unit)))
            _ba = abs(np.rad2deg(np.arctan(abs(prev_blue_slope)   * x_per_unit / y_per_unit)))
            angle_ready = max(_pa, _ba) >= min_entry_angle
        else:
            angle_ready = True

        # --- BUY signals ---
        if pos != 1 and sig_type[i] == 0 and not liquidated and angle_ready:
            if pos == 2 and reversal_blocked:
                pending_buy = False
            else:
                buy_triggered = False
                if confirmation_bars >= 1 and pending_buy:
                    buy_triggered = close > pending_ray_val
                    pending_buy = False
                elif confirmation_bars >= 1:
                    new_cross = False
                    if prev_close <= prev_orange and close > prev_orange:
                        new_cross = True; pending_ray_val = prev_orange
                    if not new_cross:
                        pa = abs(np.rad2deg(np.arctan(abs(prev_purple_slope) * x_per_unit / y_per_unit)))
                        if pa < steep_angle_threshold and prev_close <= prev_purple and close > prev_purple:
                            if abs(close - curr_orange) > proximity_points:
                                new_cross = True; pending_ray_val = prev_purple
                    if not new_cross and i > 0 and not np.isnan(magenta_vals[i-1]):
                        pm = magenta_vals[i-1]; ms = magenta_slopes[i-1]
                        ma = abs(np.rad2deg(np.arctan(abs(ms) * x_per_unit / y_per_unit))) if not np.isnan(ms) else 999.0
                        if ma < steep_angle_threshold and prev_close <= pm and close > pm:
                            if abs(close - curr_orange) > proximity_points:
                                new_cross = True; pending_ray_val = pm
                    if new_cross: pending_buy = True; pending_sell = False
                else:
                    if prev_close <= prev_orange and close > prev_orange:
                        purple_ang = abs(np.rad2deg(np.arctan(abs(prev_purple_slope) * x_per_unit / y_per_unit)))
                        strong_downtrend = (first_entry_steep_only and not first_trade_done and
                                            prev_purple_slope < 0.0 and purple_ang >= steep_angle_threshold * 0.5)
                        if not strong_downtrend:
                            buy_triggered = True
                    if not buy_triggered:
                        pa = abs(np.rad2deg(np.arctan(abs(prev_purple_slope) * x_per_unit / y_per_unit)))
                        if pa < steep_angle_threshold and prev_close <= prev_purple and close > prev_purple:
                            if abs(close - curr_orange) > proximity_points:
                                buy_triggered = True
                    if not buy_triggered and i > 0 and not np.isnan(magenta_vals[i-1]):
                        pm = magenta_vals[i-1]; ms = magenta_slopes[i-1]
                        ma = abs(np.rad2deg(np.arctan(abs(ms) * x_per_unit / y_per_unit))) if not np.isnan(ms) else 999.0
                        if ma < steep_angle_threshold and prev_close <= pm and close > pm:
                            if abs(close - curr_orange) > proximity_points:
                                buy_triggered = True
                if buy_triggered:
                    if pos == 2: session_pl += entry_price - close
                    sig_type[i] = 1; sig_price[i] = close
                    if is_last: pos = 0; entry_price = 0.0; entry_time_num = 0.0
                    else: pos = 1; entry_price = close; entry_time_num = times_num[i]; first_trade_done = True

        # --- SELL signals ---
        if pos != 2 and sig_type[i] == 0 and not liquidated and angle_ready:
            if pos == 1 and reversal_blocked:
                pending_sell = False
            else:
                sell_triggered = False
                if confirmation_bars >= 1 and pending_sell:
                    sell_triggered = close < pending_ray_val
                    pending_sell = False
                elif confirmation_bars >= 1:
                    new_cross = False
                    if prev_close >= prev_yellow and close < prev_yellow:
                        new_cross = True; pending_ray_val = prev_yellow
                    if not new_cross:
                        ba = abs(np.rad2deg(np.arctan(abs(prev_blue_slope) * x_per_unit / y_per_unit)))
                        if ba < steep_angle_threshold and prev_close >= prev_blue and close < prev_blue:
                            if abs(close - curr_yellow) > proximity_points:
                                new_cross = True; pending_ray_val = prev_blue
                    if not new_cross and i > 0 and not np.isnan(lime_vals[i-1]):
                        pl2 = lime_vals[i-1]; ls = lime_slopes_arr[i-1]
                        la = abs(np.rad2deg(np.arctan(abs(ls) * x_per_unit / y_per_unit))) if not np.isnan(ls) else 999.0
                        if la < steep_angle_threshold and prev_close >= pl2 and close < pl2:
                            if abs(close - curr_yellow) > proximity_points:
                                new_cross = True; pending_ray_val = pl2
                    if new_cross: pending_sell = True; pending_buy = False
                else:
                    if prev_close >= prev_yellow and close < prev_yellow:
                        blue_ang = abs(np.rad2deg(np.arctan(abs(prev_blue_slope) * x_per_unit / y_per_unit)))
                        strong_uptrend = (first_entry_steep_only and not first_trade_done and
                                          prev_blue_slope > 0.0 and blue_ang >= steep_angle_threshold * 0.5)
                        if not strong_uptrend:
                            sell_triggered = True
                    if not sell_triggered:
                        ba = abs(np.rad2deg(np.arctan(abs(prev_blue_slope) * x_per_unit / y_per_unit)))
                        if ba < steep_angle_threshold and prev_close >= prev_blue and close < prev_blue:
                            if abs(close - curr_yellow) > proximity_points:
                                sell_triggered = True
                    if not sell_triggered and i > 0 and not np.isnan(lime_vals[i-1]):
                        pl2 = lime_vals[i-1]; ls = lime_slopes_arr[i-1]
                        la = abs(np.rad2deg(np.arctan(abs(ls) * x_per_unit / y_per_unit))) if not np.isnan(ls) else 999.0
                        if la < steep_angle_threshold and prev_close >= pl2 and close < pl2:
                            if abs(close - curr_yellow) > proximity_points:
                                sell_triggered = True
                if sell_triggered:
                    if pos == 1: session_pl += close - entry_price
                    sig_type[i] = 2; sig_price[i] = close
                    if is_last: pos = 0; entry_price = 0.0; entry_time_num = 0.0
                    else: pos = 2; entry_price = close; entry_time_num = times_num[i]; first_trade_done = True

    return sig_type, sig_price, sig_liq


def run_trading_algo_fast(
    data: pd.DataFrame,
    target_date: str,
    start_time: str = "09:30",
    end_time: str = "10:00",
    config: Optional[AlgoConfig] = None,
) -> pd.DataFrame:
    """Exact same logic as run_trading_algo but with numpy inner loops."""

    if data is None or data.empty:
        raise ValueError("run_trading_algo_fast expected non-empty intraday data")

    full_data = data.copy()
    est = pytz.timezone("US/Eastern")
    try:
        if full_data.index.tz is None:
            full_data.index = pd.to_datetime(full_data.index, errors="coerce").tz_localize(est)
        else:
            full_data.index = pd.to_datetime(full_data.index).tz_convert(est)
    except:
        pass

    cfg = config or AlgoConfig()
    n = len(full_data)

    if cfg.warmup_minutes is not None:
        cutoff_time = full_data.index[0] + pd.Timedelta(minutes=cfg.warmup_minutes)
    else:
        cutoff_time = pd.Timestamp(f"{target_date} {start_time}:00", tz=est) + pd.Timedelta(minutes=8)

    # --- Extract numpy arrays ONCE ---
    highs_arr  = full_data["High"].values.astype(np.float64)
    lows_arr   = full_data["Low"].values.astype(np.float64)
    closes_arr = full_data["Close"].values.astype(np.float64)
    times_idx  = full_data.index  # keep as DatetimeIndex for mdates
    times_num  = np.array([mdates.date2num(t) for t in times_idx])

    # Aspect ratio — match original TradingAlgo.py exactly
    _ax_w_in = 16.0 * (0.85 - 0.125)
    _ax_h_in = 9.0 * (0.88 - 0.11)
    _x_range = 75 / (24 * 60)
    _y_range = highs_arr.max() + 20.0 - (lows_arr.min() - 20.0)
    x_per_unit = _x_range / _ax_w_in
    y_per_unit = _y_range / _ax_h_in

    # Find cutoff index
    cutoff_idx = 0
    for i in range(n):
        if times_idx[i] >= cutoff_time:
            cutoff_idx = i; break

    # --- Compute ALL rays via Numba ---
    orange_slope_val = -np.tan(np.deg2rad(cfg.orange_angle)) * (y_per_unit / x_per_unit)
    yellow_slope_val =  np.tan(np.deg2rad(cfg.yellow_angle)) * (y_per_unit / x_per_unit)

    (orange_vals, yellow_vals, purple_vals, blue_vals,
     purple_slopes, blue_slopes, purple_start_prices, blue_start_prices,
     magenta_vals, magenta_slopes, lime_vals, lime_slopes_arr,
     p_anchor_p, p_anchor_idx, b_anchor_p, b_anchor_idx) = _compute_rays_nb(
        n, highs_arr, lows_arr, closes_arr, times_num,
        orange_slope_val, yellow_slope_val,
    )

    # --- Signal detection — Numba compiled ---
    sig_type, sig_price, sig_liq = _run_signals_nb(
        n, cutoff_idx,
        closes_arr, highs_arr, lows_arr, times_num,
        orange_vals, yellow_vals, purple_vals, blue_vals,
        orange_slope_val, yellow_slope_val,
        purple_slopes, blue_slopes,
        magenta_vals, magenta_slopes,
        lime_vals, lime_slopes_arr,
        x_per_unit, y_per_unit,
        cfg.steep_angle_threshold, cfg.proximity_points,
        cfg.min_reversal_minutes, cfg.confirmation_bars,
        1 if cfg.first_entry_steep_only else 0,
        cfg.min_entry_angle,
    )

    # Convert numpy signal arrays back to dicts for _build_signals_frame
    buy_signals: Dict = {}
    sell_signals: Dict = {}
    liquidation_timestamps: set = set()
    for i in range(n):
        if sig_type[i] == 1:
            buy_signals[times_idx[i]] = sig_price[i]
            if sig_liq[i]: liquidation_timestamps.add(times_idx[i])
        elif sig_type[i] == 2:
            sell_signals[times_idx[i]] = sig_price[i]
            if sig_liq[i]: liquidation_timestamps.add(times_idx[i])

    # Build result DataFrame (same format as original)
    trading_halted = False; halt_time = None
    result = _build_signals_frame(full_data, buy_signals, sell_signals, trading_halted, halt_time, liquidation_timestamps)


    result["orange_ray"] = orange_vals
    result["yellow_ray"] = yellow_vals
    result["purple_ray"] = purple_vals
    result["blue_ray"]   = blue_vals
    result["magenta_ray"] = np.nan
    result["lime_ray"]    = np.nan

    result["orange_slope"] = orange_slope_val
    result["yellow_slope"] = yellow_slope_val
    result["purple_slope"] = purple_slopes
    result["blue_slope"]   = blue_slopes

    # Minimal metadata for compatibility
    result["purple_anchor_price"] = p_anchor_p
    result["purple_anchor_time"]  = times_idx[p_anchor_idx]
    result["blue_anchor_price"]   = b_anchor_p
    result["blue_anchor_time"]    = times_idx[b_anchor_idx]

    # Ray start data — anchor price is where the ray originates, end price is where it is at session end
    result["orange_ray_start_price"] = orange_vals[0]   # ray starts at first bar's anchor
    result["orange_ray_start_time"]  = times_idx[0]
    result["yellow_ray_start_price"] = yellow_vals[0]
    result["yellow_ray_start_time"]  = times_idx[0]
    result["purple_ray_start_price"] = purple_start_prices
    result["purple_ray_start_time"]  = [times_idx[0]] * n
    result["blue_ray_start_price"]   = blue_start_prices
    result["blue_ray_start_time"]    = [times_idx[0]] * n

    result["orange_angle"] = _display_angle_from_slope(orange_slope_val, x_per_unit, y_per_unit)
    result["yellow_angle"] = _display_angle_from_slope(yellow_slope_val, x_per_unit, y_per_unit)
    result["purple_angle"] = [_display_angle_from_slope(s, x_per_unit, y_per_unit) for s in purple_slopes]
    result["blue_angle"]   = [_display_angle_from_slope(s, x_per_unit, y_per_unit) for s in blue_slopes]

    _end_num = times_num[-1]
    result["orange_ray_end_price"] = orange_vals[-1]
    result["yellow_ray_end_price"] = yellow_vals[-1]
    result["purple_ray_end_price"] = purple_vals[-1]
    result["blue_ray_end_price"]   = blue_vals[-1]

    # Display layer pre-computations
    result["y_min"] = lows_arr.min() - 20.0
    result["y_max"] = highs_arr.max() + 20.0
    result["session_open"] = closes_arr[0]
    result["rolling_price_change"] = closes_arr - closes_arr[0]
    result["rolling_max_high"] = np.maximum.accumulate(highs_arr)
    result["rolling_min_low"]  = np.minimum.accumulate(lows_arr)
    result["rolling_range"]    = result["rolling_max_high"] - result["rolling_min_low"]

    _max_t = []; _min_t = []; _rh = -1e30; _rl = 1e30; _lt = times_idx[0]; _mt = times_idx[0]
    for i in range(n):
        if highs_arr[i] >= _rh: _rh = highs_arr[i]; _lt = times_idx[i]
        if lows_arr[i] <= _rl: _rl = lows_arr[i]; _mt = times_idx[i]
        _max_t.append(_lt); _min_t.append(_mt)
    result["rolling_max_high_time"] = _max_t
    result["rolling_min_low_time"]  = _min_t
    result["rolling_buy_count"]  = (result["signal"] == "BUY").cumsum().astype(int)
    result["rolling_sell_count"] = (result["signal"] == "SELL").cumsum().astype(int)

    return result
