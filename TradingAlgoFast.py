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

    # --- Pre-compute ALL ray values using numpy ---
    # Orange ray
    orange_slope_val = -np.tan(np.deg2rad(cfg.orange_angle)) * (y_per_unit / x_per_unit)
    orange_vals = np.zeros(n)
    o_anchor_p = highs_arr[0]; o_anchor_t = times_num[0]
    for i in range(n):
        if highs_arr[i] > o_anchor_p:
            o_anchor_p = highs_arr[i]; o_anchor_t = times_num[i]
        orange_vals[i] = o_anchor_p + orange_slope_val * (times_num[i] - o_anchor_t)

    # Yellow ray
    yellow_slope_val = np.tan(np.deg2rad(cfg.yellow_angle)) * (y_per_unit / x_per_unit)
    yellow_vals = np.zeros(n)
    y_anchor_p = lows_arr[0]; y_anchor_t = times_num[0]
    for i in range(n):
        if lows_arr[i] < y_anchor_p:
            y_anchor_p = lows_arr[i]; y_anchor_t = times_num[i]
        yellow_vals[i] = y_anchor_p + yellow_slope_val * (times_num[i] - y_anchor_t)

    # Purple/blue rays — Numba-compiled trendline fitting
    purple_vals = np.full(n, highs_arr[0])
    blue_vals   = np.full(n, lows_arr[0])
    p_anchor_p = highs_arr[0]; p_anchor_idx = 0
    b_anchor_p = lows_arr[0];  b_anchor_idx = 0

    # Store ray metadata for each bar (for signal check timing)
    # purple_vals[i] = value AFTER update_all_rays at bar i
    # Signal check at bar i+1 uses purple_vals[i] projected to bar i
    purple_start_prices = np.full(n, highs_arr[0])
    purple_start_times  = np.full(n, times_num[0])
    purple_slopes       = np.zeros(n)
    blue_start_prices   = np.full(n, lows_arr[0])
    blue_start_times    = np.full(n, times_num[0])
    blue_slopes         = np.zeros(n)

    for i in range(n):
        # Update anchors incrementally — only on strictly new high/low (matches original)
        if highs_arr[i] > p_anchor_p:
            p_anchor_p = highs_arr[i]; p_anchor_idx = i

        if lows_arr[i] < b_anchor_p:
            b_anchor_p = lows_arr[i]; b_anchor_idx = i

        # Purple and blue windows — if EITHER is too small, skip BOTH (matches original)
        pw_start = p_anchor_idx
        bw_start = b_anchor_idx
        pw_len = i + 1 - pw_start
        bw_len = i + 1 - bw_start

        if pw_len >= 2 and bw_len >= 2:
            # Purple trendline
            pw_h = highs_arr[pw_start:i+1]
            pw_l = lows_arr[pw_start:i+1]
            pw_c = closes_arr[pw_start:i+1]
            s_slope_nb, s_int_nb, r_slope_nb, r_int_nb = _fit_trendlines_nb(pw_h, pw_l, pw_c)
            r_slope_idx = r_slope_nb; r_intercept = r_int_nb
            time_step = times_num[pw_start+1] - times_num[pw_start]
            if time_step == 0: time_step = 1.0
            r_slope_time = r_slope_idx / time_step
            purple_start_prices[i] = r_intercept
            purple_start_times[i]  = times_num[pw_start]
            purple_slopes[i]       = r_slope_time
            purple_vals[i] = r_intercept + r_slope_time * (times_num[i] - times_num[pw_start])

            # Blue trendline
            bw_h = highs_arr[bw_start:i+1]
            bw_l = lows_arr[bw_start:i+1]
            bw_c = closes_arr[bw_start:i+1]
            s_slope_nb2, s_int_nb2, r_slope_nb2, r_int_nb2 = _fit_trendlines_nb(bw_h, bw_l, bw_c)
            s_slope_idx = s_slope_nb2; s_intercept = s_int_nb2
            time_step = times_num[bw_start+1] - times_num[bw_start]
            if time_step == 0: time_step = 1.0
            s_slope_time = s_slope_idx / time_step
            blue_start_prices[i] = s_intercept
            blue_start_times[i]  = times_num[bw_start]
            blue_slopes[i]       = s_slope_time
            blue_vals[i] = s_intercept + s_slope_time * (times_num[i] - times_num[bw_start])
        else:
            # Either window too small — keep previous slope, project to current time
            if i > 0:
                purple_slopes[i] = purple_slopes[i-1]
                purple_start_prices[i] = purple_start_prices[i-1]
                purple_start_times[i]  = purple_start_times[i-1]
                purple_vals[i] = purple_start_prices[i-1] + purple_slopes[i-1] * (times_num[i] - purple_start_times[i-1])
                blue_slopes[i] = blue_slopes[i-1]
                blue_start_prices[i] = blue_start_prices[i-1]
                blue_start_times[i]  = blue_start_times[i-1]
                blue_vals[i] = blue_start_prices[i-1] + blue_slopes[i-1] * (times_num[i] - blue_start_times[i-1])

    # --- Magenta/lime swing ray computation ---
    SWING_THRESHOLD = 50.0
    mag_anchor_price = None; mag_anchor_idx = -1; mag_slope_frozen = False; mag_slope = 0.0
    lime_anchor_price = None; lime_anchor_idx = -1; lime_slope_frozen = False; lime_slope = 0.0
    magenta_vals = np.full(n, np.nan)
    lime_vals    = np.full(n, np.nan)
    magenta_slopes = np.full(n, np.nan)
    lime_slopes_arr = np.full(n, np.nan)
    # Track best candidate for slope (highest high below anchor / lowest low above anchor)
    _mag_best_h = -1e9; _mag_best_idx = -1
    _lime_best_l = 1e9; _lime_best_idx = -1

    for i in range(n):
        # Only check bar i-1 as a new swing (it just got confirmed by bar i)
        if i >= 2:
            j = i - 1
            if j < n - 1:
                h = highs_arr[j]; h_prev = highs_arr[j-1]; h_next = highs_arr[j+1]
                if h - h_prev >= SWING_THRESHOLD and h - h_next >= SWING_THRESHOLD:
                    if mag_anchor_price is None or h > mag_anchor_price:
                        mag_anchor_price = h; mag_anchor_idx = j; mag_slope_frozen = False
                        _mag_best_h = -1e9; _mag_best_idx = -1  # reset candidate search

                lo = lows_arr[j]; lo_prev = lows_arr[j-1]; lo_next = lows_arr[j+1]
                if lo_prev - lo >= SWING_THRESHOLD and lo_next - lo >= SWING_THRESHOLD:
                    if lime_anchor_price is None or lo < lime_anchor_price:
                        lime_anchor_price = lo; lime_anchor_idx = j; lime_slope_frozen = False
                        _lime_best_l = 1e9; _lime_best_idx = -1

        # Build magenta ray — only check new bar i as candidate
        if mag_anchor_idx >= 0 and not mag_slope_frozen:
            if i > mag_anchor_idx and highs_arr[i] < mag_anchor_price and highs_arr[i] > _mag_best_h:
                _mag_best_h = highs_arr[i]; _mag_best_idx = i
            if _mag_best_idx >= 0:
                dt = times_num[_mag_best_idx] - times_num[mag_anchor_idx]
                if dt != 0:
                    mag_slope = (_mag_best_h - mag_anchor_price) / dt
                    mag_slope_frozen = True

        if mag_slope_frozen and mag_anchor_idx >= 0:
            magenta_vals[i] = mag_anchor_price + mag_slope * (times_num[i] - times_num[mag_anchor_idx])
            magenta_slopes[i] = mag_slope

        # Build lime ray — only check new bar i as candidate
        if lime_anchor_idx >= 0 and not lime_slope_frozen:
            if i > lime_anchor_idx and lows_arr[i] > lime_anchor_price and lows_arr[i] < _lime_best_l:
                _lime_best_l = lows_arr[i]; _lime_best_idx = i
            if _lime_best_idx >= 0:
                dt = times_num[_lime_best_idx] - times_num[lime_anchor_idx]
                if dt != 0:
                    lime_slope = (_lime_best_l - lime_anchor_price) / dt
                    lime_slope_frozen = True

        if lime_slope_frozen and lime_anchor_idx >= 0:
            lime_vals[i] = lime_anchor_price + lime_slope * (times_num[i] - times_num[lime_anchor_idx])
            lime_slopes_arr[i] = lime_slope

    # --- Signal detection using pre-computed arrays ---
    buy_signals: Dict = {}
    sell_signals: Dict = {}
    liquidation_timestamps: set = set()
    session_realized_pl = 0.0
    temp_position = "flat"
    temp_entry_price = None
    temp_entry_time = None
    # Confirmation bar state: pending signal waits for next bar confirmation
    _pending_buy = False   # True if a BUY cross happened on the previous bar
    _pending_sell = False  # True if a SELL cross happened on the previous bar
    _pending_ray_val = 0.0 # The ray value the close must stay beyond

    for i in range(max(cutoff_idx, 3), n):
        time = times_idx[i]
        current_close = closes_arr[i]
        prev_close    = closes_arr[i-1]

        # Ray values: signal check uses values from bar i-1's update
        prev_orange = orange_vals[i-1]
        prev_yellow = yellow_vals[i-1]
        prev_purple = purple_vals[i-1]
        prev_blue   = blue_vals[i-1]
        # curr_orange/curr_yellow: project from bar i-1's state to bar i's time
        # (matches original which computes these BEFORE update_all_rays at bar i)
        _dt = times_num[i] - times_num[i-1]
        curr_orange = orange_vals[i-1] + orange_slope_val * _dt
        curr_yellow = yellow_vals[i-1] + yellow_slope_val * _dt

        # Previous slopes for angle calculation
        prev_purple_slope = purple_slopes[i-1] if i > 0 else 0.0
        prev_blue_slope   = blue_slopes[i-1] if i > 0 else 0.0

        liquidated_this_bar = False
        is_last_bar = (i == n - 1)

        # --- Trailing stop v3 ---
        if not liquidated_this_bar and temp_position != "flat" and temp_entry_price is not None and i >= 5:
            if temp_position == "long":
                unrealized_profit = current_close - temp_entry_price
            else:
                unrealized_profit = temp_entry_price - current_close

            if unrealized_profit >= 75:
                has_hh = False; conf_price = None; conf_time = None
                start_j = max(0, i - 10)
                if temp_position == "long" and i >= 4:
                    for k in range(i, start_j + 1, -1):
                        if k >= 2 and highs_arr[k] > highs_arr[k-2]:
                            mid_low = lows_arr[k-1]
                            if highs_arr[k] - mid_low >= 30:
                                has_hh = True; conf_price = mid_low; conf_time = times_num[k-1]; break
                elif temp_position == "short" and i >= 4:
                    for k in range(i, start_j + 1, -1):
                        if k >= 2 and lows_arr[k] < lows_arr[k-2]:
                            mid_high = highs_arr[k-1]
                            if mid_high - lows_arr[k] >= 30:
                                has_hh = True; conf_price = mid_high; conf_time = times_num[k-1]; break

                if has_hh and unrealized_profit >= 150: trail_angle = 60.0
                elif has_hh: trail_angle = 50.0
                else: trail_angle = 40.0
                trailing_slope = np.tan(np.deg2rad(trail_angle)) * (y_per_unit / x_per_unit)

                anchor_p = conf_price; anchor_t = conf_time
                if anchor_p is None:
                    SWING_MIN = 50.0
                    for j in range(max(1, i-15), i):
                        if j >= n - 1: continue
                        if temp_position == "long":
                            lo = lows_arr[j]
                            if lows_arr[j-1] - lo >= SWING_MIN * 0.3 and lows_arr[j+1] - lo >= SWING_MIN * 0.3:
                                if anchor_p is None or lo > anchor_p:
                                    anchor_p = lo; anchor_t = times_num[j]
                        else:
                            hi = highs_arr[j]
                            if hi - highs_arr[j-1] >= SWING_MIN * 0.3 and hi - highs_arr[j+1] >= SWING_MIN * 0.3:
                                if anchor_p is None or hi < anchor_p:
                                    anchor_p = hi; anchor_t = times_num[j]

                if anchor_p is not None and anchor_t is not None:
                    t_diff = times_num[i] - anchor_t
                    if t_diff > 0:
                        if temp_position == "long":
                            stop_level = anchor_p + trailing_slope * t_diff
                            if current_close < stop_level:
                                session_realized_pl += current_close - temp_entry_price
                                sell_signals[time] = current_close
                                liquidation_timestamps.add(time)
                                temp_position = "flat"; temp_entry_price = None; temp_entry_time = None
                                liquidated_this_bar = True
                        else:
                            stop_level = anchor_p - trailing_slope * t_diff
                            if current_close > stop_level:
                                session_realized_pl += temp_entry_price - current_close
                                buy_signals[time] = current_close
                                liquidation_timestamps.add(time)
                                temp_position = "flat"; temp_entry_price = None; temp_entry_time = None
                                liquidated_this_bar = True

        # Reversal guard
        mins_since_entry = (time - temp_entry_time).total_seconds() / 60 if temp_entry_time else 999
        orange_cross_buy  = prev_close <= prev_orange and current_close > prev_orange
        yellow_cross_sell = prev_close >= prev_yellow and current_close < prev_yellow
        safety_override = ((temp_position == "short" and orange_cross_buy) or
                           (temp_position == "long" and yellow_cross_sell))
        reversal_blocked = (cfg.min_reversal_minutes > 0 and
                            mins_since_entry < cfg.min_reversal_minutes and
                            not safety_override)

        # BUY signals
        if temp_position != "long" and time not in buy_signals and not liquidated_this_bar:
            if temp_position == "short" and reversal_blocked:
                _pending_buy = False
            else:
                buy_triggered = False

                # Check confirmation bar: if pending from last bar, confirm now
                if cfg.confirmation_bars >= 1 and _pending_buy:
                    if current_close > _pending_ray_val:
                        buy_triggered = True
                    _pending_buy = False
                elif cfg.confirmation_bars >= 1:
                    # Check for new cross — set pending instead of triggering
                    _new_cross = False
                    if prev_close <= prev_orange and current_close > prev_orange:
                        _new_cross = True; _pending_ray_val = prev_orange
                    if not _new_cross:
                        purple_angle = _display_angle_from_slope(prev_purple_slope, x_per_unit, y_per_unit)
                        if purple_angle < cfg.steep_angle_threshold and prev_close <= prev_purple and current_close > prev_purple:
                            if abs(current_close - curr_orange) > cfg.proximity_points:
                                _new_cross = True; _pending_ray_val = prev_purple
                    if not _new_cross and i > 0 and not np.isnan(magenta_vals[i-1]):
                        prev_mag = magenta_vals[i-1]
                        _mag_slope = magenta_slopes[i-1]
                        mag_angle = _display_angle_from_slope(_mag_slope, x_per_unit, y_per_unit) if not np.isnan(_mag_slope) else 999.0
                        if mag_angle < cfg.steep_angle_threshold and prev_close <= prev_mag and current_close > prev_mag:
                            if abs(current_close - curr_orange) > cfg.proximity_points:
                                _new_cross = True; _pending_ray_val = prev_mag
                    if _new_cross:
                        _pending_buy = True; _pending_sell = False
                else:
                    # No confirmation — original behavior
                    if prev_close <= prev_orange and current_close > prev_orange:
                        buy_triggered = True
                    if not buy_triggered:
                        purple_angle = _display_angle_from_slope(prev_purple_slope, x_per_unit, y_per_unit)
                        if purple_angle < cfg.steep_angle_threshold and prev_close <= prev_purple and current_close > prev_purple:
                            if abs(current_close - curr_orange) > cfg.proximity_points:
                                buy_triggered = True
                    if not buy_triggered and i > 0 and not np.isnan(magenta_vals[i-1]):
                        prev_mag = magenta_vals[i-1]
                        _mag_slope = magenta_slopes[i-1]
                        mag_angle = _display_angle_from_slope(_mag_slope, x_per_unit, y_per_unit) if not np.isnan(_mag_slope) else 999.0
                        if mag_angle < cfg.steep_angle_threshold and prev_close <= prev_mag and current_close > prev_mag:
                            if abs(current_close - curr_orange) > cfg.proximity_points:
                                buy_triggered = True

                if buy_triggered:
                    if temp_position == "short" and temp_entry_price is not None:
                        session_realized_pl += temp_entry_price - current_close
                    buy_signals[time] = current_close
                    if is_last_bar:
                        temp_position = "flat"; temp_entry_price = None; temp_entry_time = None
                    else:
                        temp_position = "long"; temp_entry_price = current_close; temp_entry_time = time

        # SELL signals
        if temp_position != "short" and time not in sell_signals and not liquidated_this_bar:
            if temp_position == "long" and reversal_blocked:
                _pending_sell = False
            else:
                sell_triggered = False

                # Check confirmation bar: if pending from last bar, confirm now
                if cfg.confirmation_bars >= 1 and _pending_sell:
                    if current_close < _pending_ray_val:
                        sell_triggered = True
                    _pending_sell = False
                elif cfg.confirmation_bars >= 1:
                    # Check for new cross — set pending instead of triggering
                    _new_cross = False
                    if prev_close >= prev_yellow and current_close < prev_yellow:
                        _new_cross = True; _pending_ray_val = prev_yellow
                    if not _new_cross:
                        blue_angle = _display_angle_from_slope(prev_blue_slope, x_per_unit, y_per_unit)
                        if blue_angle < cfg.steep_angle_threshold and prev_close >= prev_blue and current_close < prev_blue:
                            if abs(current_close - curr_yellow) > cfg.proximity_points:
                                _new_cross = True; _pending_ray_val = prev_blue
                    if not _new_cross and i > 0 and not np.isnan(lime_vals[i-1]):
                        prev_lime = lime_vals[i-1]
                        _lime_slope = lime_slopes_arr[i-1]
                        lime_angle = _display_angle_from_slope(_lime_slope, x_per_unit, y_per_unit) if not np.isnan(_lime_slope) else 999.0
                        if lime_angle < cfg.steep_angle_threshold and prev_close >= prev_lime and current_close < prev_lime:
                            if abs(current_close - curr_yellow) > cfg.proximity_points:
                                _new_cross = True; _pending_ray_val = prev_lime
                    if _new_cross:
                        _pending_sell = True; _pending_buy = False
                else:
                    # No confirmation — original behavior
                    if prev_close >= prev_yellow and current_close < prev_yellow:
                        sell_triggered = True
                    if not sell_triggered:
                        blue_angle = _display_angle_from_slope(prev_blue_slope, x_per_unit, y_per_unit)
                        if blue_angle < cfg.steep_angle_threshold and prev_close >= prev_blue and current_close < prev_blue:
                            if abs(current_close - curr_yellow) > cfg.proximity_points:
                                sell_triggered = True
                    if not sell_triggered and i > 0 and not np.isnan(lime_vals[i-1]):
                        prev_lime = lime_vals[i-1]
                        _lime_slope = lime_slopes_arr[i-1]
                        lime_angle = _display_angle_from_slope(_lime_slope, x_per_unit, y_per_unit) if not np.isnan(_lime_slope) else 999.0
                        if lime_angle < cfg.steep_angle_threshold and prev_close >= prev_lime and current_close < prev_lime:
                            if abs(current_close - curr_yellow) > cfg.proximity_points:
                                sell_triggered = True

                if sell_triggered:
                    if temp_position == "long" and temp_entry_price is not None:
                        session_realized_pl += current_close - temp_entry_price
                    sell_signals[time] = current_close
                    if is_last_bar:
                        temp_position = "flat"; temp_entry_price = None; temp_entry_time = None
                    else:
                        temp_position = "short"; temp_entry_price = current_close; temp_entry_time = time

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

    # Ray start data
    result["orange_ray_start_price"] = orange_vals  # simplified
    result["orange_ray_start_time"]  = times_idx[0]
    result["yellow_ray_start_price"] = yellow_vals
    result["yellow_ray_start_time"]  = times_idx[0]
    result["purple_ray_start_price"] = purple_start_prices
    result["purple_ray_start_time"]  = [times_idx[0]] * n  # simplified
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
