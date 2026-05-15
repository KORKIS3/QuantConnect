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
    min_reversal_minutes: int = 0
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
    steep_line_threshold: float = 50.0    # pts above/below primary line to spawn steeper line
    steep_line_proximity: float = 5.0     # suppress steep line reversal if close is within N pts of original primary ray
    steep_line_exit_only: bool = False    # if True, steep line cross exits to flat instead of reversing
    steep_line_reentry: bool = False      # allow steep line cross to trigger fresh entry when flat (after first trade)
    disable_trailing_stop: bool = False   # set True to test steep lines without trailing stop v4
    reanchor_blue_purple: bool = True     # re-anchor blue/purple from next swing point when invalidated mid-session
    reanchor_min_bars: int = 30           # minimum bars after invalidation before re-anchoring (prevents thrashing)
    reanchor_swing_threshold: float = 5.0 # min pts for a swing low/high to qualify as re-anchor point


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
            elif position == "long" and entry_price is not None and is_liq:
                cumulative_realized_pl += buy_price - entry_price  # Close LONG position
            position   = "flat" if is_liq else "long"
            entry_price = None  if is_liq else buy_price

        if is_sell:
            sell_price = float(sell_signals[ts])
            if position == "long" and entry_price is not None:
                cumulative_realized_pl += sell_price - entry_price
            elif position == "short" and entry_price is not None and is_liq:
                cumulative_realized_pl += entry_price - sell_price  # Close SHORT position
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
    warmup_bars, steep_line_threshold,
    reanchor_blue_purple=1, reanchor_min_bars=30, reanchor_swing_threshold=5.0,
):
    """Compute all ray values in a single Numba-compiled pass.
    Returns: orange_vals, yellow_vals, purple_vals, blue_vals,
             purple_slopes, blue_slopes, purple_start_prices, blue_start_prices,
             magenta_vals, magenta_slopes, lime_vals, lime_slopes_arr,
             p_anchor_p, p_anchor_idx, b_anchor_p, b_anchor_idx
    """
    # --- Orange ray ---
    orange_vals          = np.zeros(n)
    orange_anchor_prices = np.zeros(n)
    orange_anchor_times  = np.zeros(n)
    o_anchor_p = highs_arr[0]; o_anchor_t = times_num[0]; o_anchor_i = 0
    for i in range(n):
        if highs_arr[i] > o_anchor_p:
            o_anchor_p = highs_arr[i]; o_anchor_t = times_num[i]; o_anchor_i = i
        orange_vals[i]          = o_anchor_p + orange_slope_val * (times_num[i] - o_anchor_t)
        orange_anchor_prices[i] = o_anchor_p
        orange_anchor_times[i]  = float(o_anchor_i)  # store bar index

    # --- Yellow ray ---
    yellow_vals          = np.zeros(n)
    yellow_anchor_prices = np.zeros(n)
    yellow_anchor_times  = np.zeros(n)
    y_anchor_p = lows_arr[0]; y_anchor_t = times_num[0]; y_anchor_i = 0
    for i in range(n):
        if lows_arr[i] < y_anchor_p:
            y_anchor_p = lows_arr[i]; y_anchor_t = times_num[i]; y_anchor_i = i
        yellow_vals[i]          = y_anchor_p + yellow_slope_val * (times_num[i] - y_anchor_t)
        yellow_anchor_prices[i] = y_anchor_p
        yellow_anchor_times[i]  = float(y_anchor_i)  # store bar index

    # --- Purple/blue rays (two-point frozen straight lines) ---
    # Blue:   P1 = session low, provisional 45° slope until P2 (first confirmed higher
    #         swing low) is found, then slope is frozen.  Adjust rule: if a future bar's
    #         low pierces the line but close is above → P2 updates to that bar's low,
    #         slope recalculates and freezes again.  Invalidate if slope <= 0.
    # Purple: exact mirror (descending from session high).
    # All output is stored as per-bar arrays so the plotter just reads start/end columns.

    SWING_THRESHOLD = reanchor_swing_threshold   # min pts to qualify as a confirmed swing high/low

    # Default slopes: 45° equivalent in price/time units
    _default_blue_slope   =  np.tan(np.deg2rad(45.0)) * (yellow_slope_val / np.tan(np.deg2rad(2.5)))
    _default_purple_slope = -np.tan(np.deg2rad(45.0)) * (yellow_slope_val / np.tan(np.deg2rad(2.5)))

    # Per-bar output arrays
    purple_vals         = np.zeros(n)
    blue_vals           = np.zeros(n)
    purple_slopes       = np.zeros(n)
    blue_slopes         = np.zeros(n)
    purple_start_prices = np.zeros(n)
    blue_start_prices   = np.zeros(n)
    purple_anchor_idxs  = np.zeros(n, dtype=np.int64)
    blue_anchor_idxs    = np.zeros(n, dtype=np.int64)
    purple_end_prices   = np.zeros(n)
    blue_end_prices     = np.zeros(n)

    # Steeper line families (up to 4 each) — NaN when not active
    MAX_STEEP = 4
    STEEP_THRESHOLD = steep_line_threshold
    blue_steep_vals         = np.full((MAX_STEEP, n), np.nan)
    blue_steep_start_prices = np.full((MAX_STEEP, n), np.nan)
    blue_steep_end_prices   = np.full((MAX_STEEP, n), np.nan)
    blue_steep_p1_idxs      = np.full((MAX_STEEP, n), -1.0)   # bar index of P1
    purple_steep_vals         = np.full((MAX_STEEP, n), np.nan)
    purple_steep_start_prices = np.full((MAX_STEEP, n), np.nan)
    purple_steep_end_prices   = np.full((MAX_STEEP, n), np.nan)
    purple_steep_p1_idxs      = np.full((MAX_STEEP, n), -1.0)

    # Steeper line state: p1_idx, p1_price, p2_idx, p2_price, slope, valid
    bs_p1_idx   = np.zeros(MAX_STEEP, dtype=np.int64)
    bs_p1_price = np.zeros(MAX_STEEP)
    bs_p2_idx   = np.zeros(MAX_STEEP, dtype=np.int64)
    bs_p2_price = np.zeros(MAX_STEEP)
    bs_slope    = np.zeros(MAX_STEEP)
    bs_valid    = np.zeros(MAX_STEEP, dtype=np.int64)
    bs_count    = 0   # number of steeper blue lines active

    ps_p1_idx   = np.zeros(MAX_STEEP, dtype=np.int64)
    ps_p1_price = np.zeros(MAX_STEEP)
    ps_p2_idx   = np.zeros(MAX_STEEP, dtype=np.int64)
    ps_p2_price = np.zeros(MAX_STEEP)
    ps_slope    = np.zeros(MAX_STEEP)
    ps_valid    = np.zeros(MAX_STEEP, dtype=np.int64)
    ps_count    = 0

    # Track most recent confirmed swing low/high for steeper line anchoring
    last_sl_idx = 0; last_sl_price = lows_arr[0]
    last_sh_idx = 0; last_sh_price = highs_arr[0]

    # Last touch point on primary lines — P1 for steeper lines
    # Purple starts at session high (immediately touched), blue starts at session low (not touched until price comes down)
    b_last_touch_idx = -1; b_last_touch_price = 0.0
    p_last_touch_idx = 0; p_last_touch_price = highs_arr[0]

    # Blue state: p1_idx, p1_price, slope, p2_locked (0=provisional, 1=locked), valid
    b_p1_idx = 0; b_p1_price = lows_arr[0]; b_slope = _default_blue_slope
    b_p2_locked = 0; b_valid = 1
    b_session_low = lows_arr[0]; b_session_low_idx = 0

    # Purple state
    p_p1_idx = 0; p_p1_price = highs_arr[0]; p_slope = _default_purple_slope
    p_p2_locked = 0; p_valid = 1
    p_session_high = highs_arr[0]; p_session_high_idx = 0

    # Re-anchor state: track when each line was last invalidated so we can
    # re-anchor from the next confirmed swing point after reanchor_min_bars
    b_invalidated_at = -1   # bar index when blue was last invalidated (-1 = never)
    p_invalidated_at = -1   # bar index when purple was last invalidated (-1 = never)

    for i in range(n):
        t_i = times_num[i]

        # Track session extremes — reset line on new extreme
        if lows_arr[i] < b_session_low:
            b_session_low = lows_arr[i]; b_session_low_idx = i
            b_p1_idx = i; b_p1_price = lows_arr[i]
            b_slope = _default_blue_slope; b_p2_locked = 0; b_valid = 1

        if highs_arr[i] > p_session_high:
            p_session_high = highs_arr[i]; p_session_high_idx = i
            p_p1_idx = i; p_p1_price = highs_arr[i]
            p_slope = _default_purple_slope; p_p2_locked = 0; p_valid = 1

        # Detect swing points and lock slopes — runs during AND after warmup
        new_sl_idx = -1; new_sl_price = 0.0
        new_sh_idx = -1; new_sh_price = 0.0
        if i >= 2:
            j = i - 1
            l_j = lows_arr[j]
            if lows_arr[j-1] - l_j >= SWING_THRESHOLD and lows_arr[i] - l_j >= SWING_THRESHOLD:
                new_sl_idx = j; new_sl_price = l_j
                last_sl_idx = j; last_sl_price = l_j
            h_j = highs_arr[j]
            if h_j - highs_arr[j-1] >= SWING_THRESHOLD and h_j - highs_arr[i] >= SWING_THRESHOLD:
                new_sh_idx = j; new_sh_price = h_j
                last_sh_idx = j; last_sh_price = h_j

        # Lock purple slope to P2 (runs during warmup too)
        if p_valid == 1 and p_p2_locked == 0 and new_sh_idx >= 0:
            if new_sh_price < p_session_high and new_sh_idx > p_session_high_idx:
                dt = times_num[new_sh_idx] - times_num[p_p1_idx]
                if dt != 0.0:
                    s = (new_sh_price - p_p1_price) / dt
                    if s < 0.0:
                        p_slope = s; p_p2_locked = 1
                        p_last_touch_idx = new_sh_idx; p_last_touch_price = new_sh_price

        # Lock blue slope to P2 (runs during warmup too)
        if b_valid == 1 and b_p2_locked == 0 and new_sl_idx >= 0:
            if new_sl_price > b_session_low and new_sl_idx > b_session_low_idx:
                dt = times_num[new_sl_idx] - times_num[b_p1_idx]
                if dt != 0.0:
                    s = (new_sl_price - b_p1_price) / dt
                    if s > 0.0:
                        b_slope = s; b_p2_locked = 1
                        b_last_touch_idx = new_sl_idx; b_last_touch_price = new_sl_price

        # Before warmup ends — compute ray values using locked slope if available
        if i < warmup_bars:
            if b_p2_locked == 1:
                b_line_w = b_p1_price + b_slope * (t_i - times_num[b_p1_idx])
                # Pierce check during warmup: low below ray -> reanchor
                if lows_arr[i] < b_line_w:
                    dt = t_i - times_num[b_p1_idx]
                    if dt != 0.0:
                        ns = (lows_arr[i] - b_p1_price) / dt
                        if ns <= 0.0:
                            b_valid = 0
                        else:
                            b_slope = ns; b_line_w = b_p1_price + b_slope * (t_i - times_num[b_p1_idx])
                            b_last_touch_idx = i; b_last_touch_price = b_line_w
                blue_vals[i]         = b_line_w
                blue_slopes[i]       = b_slope
                blue_start_prices[i] = b_p1_price
                blue_anchor_idxs[i]  = b_p1_idx
                blue_end_prices[i]   = b_p1_price + b_slope * (times_num[-1] - times_num[b_p1_idx])
            else:
                blue_vals[i]         = b_p1_price
                blue_slopes[i]       = 0.0
                blue_start_prices[i] = np.nan
                blue_anchor_idxs[i]  = b_p1_idx
                blue_end_prices[i]   = np.nan
            if p_p2_locked == 1:
                p_line_w = p_p1_price + p_slope * (t_i - times_num[p_p1_idx])
                # Pierce check during warmup: high above ray -> reanchor
                if highs_arr[i] > p_line_w:
                    dt = t_i - times_num[p_p1_idx]
                    if dt != 0.0:
                        ns = (highs_arr[i] - p_p1_price) / dt
                        if ns >= 0.0:
                            p_valid = 0
                        else:
                            p_slope = ns; p_line_w = p_p1_price + p_slope * (t_i - times_num[p_p1_idx])
                            p_last_touch_idx = i; p_last_touch_price = p_line_w
                purple_vals[i]         = p_line_w
                purple_slopes[i]       = p_slope
                purple_start_prices[i] = p_p1_price
                purple_anchor_idxs[i]  = p_p1_idx
                purple_end_prices[i]   = p_p1_price + p_slope * (times_num[-1] - times_num[p_p1_idx])
            else:
                purple_vals[i]         = p_p1_price
                purple_slopes[i]       = 0.0
                purple_start_prices[i] = np.nan
                purple_anchor_idxs[i]  = p_p1_idx
                purple_end_prices[i]   = np.nan
            p_anchor_p = p_p1_price; b_anchor_p = b_p1_price
            
            # Steep line spawning during warmup (before continue)
            # Purple steep lines
            STEEP_FACTOR = 1.3
            if p_valid == 1 and p_last_touch_idx >= 0 and p_slope != 0.0:
                dist = p_last_touch_price - highs_arr[i]
                if ps_count < MAX_STEEP and dist >= STEEP_THRESHOLD:
                    already = False
                    for lx in range(ps_count):
                        if ps_p1_idx[lx] == p_last_touch_idx:
                            already = True
                    if not already:
                        ns = p_slope * STEEP_FACTOR
                        li = ps_count
                        ps_p1_idx[li] = p_last_touch_idx; ps_p1_price[li] = p_last_touch_price
                        ps_p2_idx[li] = i;                ps_p2_price[li] = p_last_touch_price + ns * (t_i - times_num[p_last_touch_idx])
                        ps_slope[li] = ns; ps_valid[li] = 1
                        ps_count += 1
            
            continue

        # Compute current blue line value
        if b_valid == 1:
            b_line_i = b_p1_price + b_slope * (t_i - times_num[b_p1_idx])
            if lows_arr[i] < b_line_i:
                dt = t_i - times_num[b_p1_idx]
                if dt != 0.0:
                    ns = (lows_arr[i] - b_p1_price) / dt
                    if ns <= 0.0:
                        b_valid = 0
                        b_invalidated_at = i
                    else:
                        b_slope = ns; b_p2_locked = 1
                        b_line_i = b_p1_price + b_slope * (t_i - times_num[b_p1_idx])
            # Record touch point whenever low is within 5pts of the line (pierce OR graze)
            if b_valid == 1 and abs(lows_arr[i] - b_line_i) <= 5.0:
                b_last_touch_idx = i; b_last_touch_price = lows_arr[i]
            blue_vals[i]         = b_line_i
            blue_slopes[i]       = b_slope
            blue_start_prices[i] = b_p1_price
            blue_anchor_idxs[i]  = b_p1_idx
            blue_end_prices[i]   = b_p1_price + b_slope * (times_num[-1] - times_num[b_p1_idx])
        else:
            # Re-anchor: if enabled and a confirmed swing low has appeared at least
            # reanchor_min_bars after invalidation, restart blue from that swing low
            if (reanchor_blue_purple == 1 and b_invalidated_at >= 0
                    and new_sl_idx >= 0
                    and new_sl_idx > b_invalidated_at
                    and (new_sl_idx - b_invalidated_at) >= reanchor_min_bars):
                b_p1_idx = new_sl_idx; b_p1_price = new_sl_price
                b_slope = _default_blue_slope; b_p2_locked = 0; b_valid = 1
                b_invalidated_at = -1
                b_last_touch_idx = new_sl_idx; b_last_touch_price = new_sl_price
                b_line_i = b_p1_price + b_slope * (t_i - times_num[b_p1_idx])
                blue_vals[i]         = b_line_i
                blue_slopes[i]       = b_slope
                blue_start_prices[i] = b_p1_price
                blue_anchor_idxs[i]  = b_p1_idx
                blue_end_prices[i]   = b_p1_price + b_slope * (times_num[-1] - times_num[b_p1_idx])
            else:
                blue_vals[i]         = blue_vals[i-1] if i > 0 else lows_arr[0]
                blue_slopes[i]       = 0.0
                blue_start_prices[i] = blue_start_prices[i-1] if i > 0 else lows_arr[0]
                blue_anchor_idxs[i]  = blue_anchor_idxs[i-1] if i > 0 else 0
                blue_end_prices[i]   = blue_end_prices[i-1] if i > 0 else lows_arr[0]

        # Compute current purple line value
        if p_valid == 1:
            p_line_i = p_p1_price + p_slope * (t_i - times_num[p_p1_idx])
            # Adjust: high pierces but close below → update P2, refreeze slope
            # Also: close above purple (with or without a buy signal) → push P2 up to bar's high
            if highs_arr[i] > p_line_i:
                dt = t_i - times_num[p_p1_idx]
                if dt != 0.0:
                    ns = (highs_arr[i] - p_p1_price) / dt
                    if ns >= 0.0:
                        p_valid = 0
                        p_invalidated_at = i
                    else:
                        p_slope = ns; p_p2_locked = 1
                        p_line_i = p_p1_price + p_slope * (t_i - times_num[p_p1_idx])
            # Record touch point whenever high is within 5pts of the line (pierce OR graze)
            # Store the purple ray value (not the high) so steeper line sits above the highs
            if p_valid == 1 and abs(highs_arr[i] - p_line_i) <= 5.0:
                p_last_touch_idx = i; p_last_touch_price = p_line_i
            purple_vals[i]         = p_line_i
            purple_slopes[i]       = p_slope
            purple_start_prices[i] = p_p1_price
            purple_anchor_idxs[i]  = p_p1_idx
            purple_end_prices[i]   = p_p1_price + p_slope * (times_num[-1] - times_num[p_p1_idx])
        else:
            # Re-anchor: if enabled and a confirmed swing high has appeared at least
            # reanchor_min_bars after invalidation, restart purple from that swing high
            if (reanchor_blue_purple == 1 and p_invalidated_at >= 0
                    and new_sh_idx >= 0
                    and new_sh_idx > p_invalidated_at
                    and (new_sh_idx - p_invalidated_at) >= reanchor_min_bars):
                p_p1_idx = new_sh_idx; p_p1_price = new_sh_price
                p_slope = _default_purple_slope; p_p2_locked = 0; p_valid = 1
                p_invalidated_at = -1
                p_last_touch_idx = new_sh_idx; p_last_touch_price = new_sh_price
                p_line_i = p_p1_price + p_slope * (t_i - times_num[p_p1_idx])
                purple_vals[i]         = p_line_i
                purple_slopes[i]       = p_slope
                purple_start_prices[i] = p_p1_price
                purple_anchor_idxs[i]  = p_p1_idx
                purple_end_prices[i]   = p_p1_price + p_slope * (times_num[-1] - times_num[p_p1_idx])
            else:
                purple_vals[i]         = purple_vals[i-1] if i > 0 else highs_arr[0]
                purple_slopes[i]       = 0.0
                purple_start_prices[i] = purple_start_prices[i-1] if i > 0 else highs_arr[0]
                purple_anchor_idxs[i]  = purple_anchor_idxs[i-1] if i > 0 else 0
                purple_end_prices[i]   = purple_end_prices[i-1] if i > 0 else highs_arr[0]

        p_anchor_p = highs_arr[p_p1_idx]
        b_anchor_p = lows_arr[b_p1_idx]

        # --- Steeper blue lines ---
        # Spawn when the LOW is STEEP_THRESHOLD pts above blue (price running up)
        # P1 = last touch point on primary blue, P2 = current bar's low
        # Progressive spawning: each new steep line spawns when price moves above the previous one
        if b_valid == 1 and lows_arr[i] > b_line_i:
            ref_val = b_line_i
            if bs_count > 0:
                # Find the highest VALID steep line to use as reference
                for lv in range(bs_count - 1, -1, -1):
                    if bs_valid[lv] == 1:
                        ref_val = bs_p1_price[lv] + bs_slope[lv] * (t_i - times_num[bs_p1_idx[lv]])
                        break
            
            # Count active (valid) steep lines
            active_count = 0
            for lv in range(bs_count):
                if bs_valid[lv] == 1:
                    active_count += 1
            
            if lows_arr[i] - ref_val >= STEEP_THRESHOLD and active_count < MAX_STEEP:
                if b_last_touch_idx >= 0 and b_last_touch_idx < i:
                    dt = t_i - times_num[b_last_touch_idx]
                    if dt != 0.0:
                        ns = (lows_arr[i] - b_last_touch_price) / dt
                        if ns > 0.0:
                            # Find first available slot (reuse invalidated slots)
                            li = -1
                            for slot in range(MAX_STEEP):
                                if slot >= bs_count or bs_valid[slot] == 0:
                                    li = slot
                                    break
                            if li >= 0:
                                bs_p1_idx[li] = b_last_touch_idx; bs_p1_price[li] = b_last_touch_price
                                bs_p2_idx[li] = i;                bs_p2_price[li] = lows_arr[i]
                                bs_slope[li]  = ns;               bs_valid[li]    = 1
                                if li >= bs_count:
                                    bs_count = li + 1

        # Update existing steeper blue lines
        for li in range(bs_count):
            if bs_valid[li] == 0:
                continue
            lv = bs_p1_price[li] + bs_slope[li] * (t_i - times_num[bs_p1_idx[li]])
            
            # Check if steep line is nearly horizontal (angle < 10 degrees)
            # For nearly horizontal lines, invalidate if low drops below
            # For steeper lines, allow slope adjustment
            price_range = highs_arr[0] - lows_arr[0]
            if price_range > 0.0:
                angle_deg = abs(np.rad2deg(np.arctan(bs_slope[li] * (times_num[-1] - times_num[0]) / price_range)))
                is_nearly_horizontal = angle_deg < 10.0
            else:
                # Zero price range - treat as horizontal
                is_nearly_horizontal = True
            
            if lows_arr[i] < lv:
                if is_nearly_horizontal:
                    # Nearly horizontal line - invalidate immediately
                    bs_valid[li] = 0
                else:
                    # Steeper line - try to adjust slope
                    dt = t_i - times_num[bs_p1_idx[li]]
                    if dt != 0.0:
                        ns = (lows_arr[i] - bs_p1_price[li]) / dt
                        if ns <= 0.0:
                            bs_valid[li] = 0
                        else:
                            bs_slope[li] = ns; lv = bs_p1_price[li] + ns * (t_i - times_num[bs_p1_idx[li]])
            
            if bs_valid[li] == 1:
                blue_steep_vals[li, i]         = lv
                blue_steep_start_prices[li, i] = bs_p1_price[li]
                blue_steep_p1_idxs[li, i]      = float(bs_p1_idx[li])
                blue_steep_end_prices[li, i]   = bs_p1_price[li] + bs_slope[li] * (times_num[-1] - times_num[bs_p1_idx[li]])

        # --- Steeper purple lines ---
        # Spawn when price has moved STEEP_THRESHOLD pts below the last touch point
        # Slope calculated as the LEAST STEEP (most negative) slope from touch point through any subsequent high
        # This ensures line stays above all highs without being unnecessarily steep
        STEEP_FACTOR = 1.3  # how much steeper than the purple ray
        if p_valid == 1 and p_last_touch_idx >= 0 and p_slope != 0.0:
            # Check distance from last touch point
            dist = p_last_touch_price - highs_arr[i]
            
            # Count active (valid) steep lines
            active_count = 0
            for lv in range(ps_count):
                if ps_valid[lv] == 1:
                    active_count += 1
            
            if active_count < MAX_STEEP and dist >= STEEP_THRESHOLD:
                already = False
                for lx in range(ps_count):
                    if ps_p1_idx[lx] == p_last_touch_idx and ps_valid[lx] == 1:
                        already = True
                if not already:
                    # Find first available slot (reuse invalidated slots)
                    li = -1
                    for slot in range(MAX_STEEP):
                        if slot >= ps_count or ps_valid[slot] == 0:
                            li = slot
                            break
                    
                    if li >= 0:
                        # Anchor at purple touch point (e.g., 10:00)
                        ps_p1_idx[li] = p_last_touch_idx
                        ps_p1_price[li] = p_last_touch_price
                        
                        # Find the LEAST STEEP slope (most negative) from touch point through any subsequent high
                        # This is the slope that stays closest to the highs without going below them
                        least_steep_slope = -1e30  # Start with very negative (very steep)
                        target_idx = i
                        
                        for j in range(p_last_touch_idx + 1, i + 1):
                            dt = times_num[j] - times_num[p_last_touch_idx]
                            if dt > 0.0:
                                slope_to_j = (highs_arr[j] - p_last_touch_price) / dt
                                # We want the LEAST STEEP (most negative, closest to 0)
                                if slope_to_j > least_steep_slope:
                                    least_steep_slope = slope_to_j
                                    target_idx = j
                        
                        # Use the least steep slope found
                        if least_steep_slope > -1e30:
                            ns = least_steep_slope
                        else:
                            ns = p_slope * STEEP_FACTOR
                        
                        ps_p2_idx[li] = target_idx
                        ps_p2_price[li] = highs_arr[target_idx]
                        ps_slope[li] = ns
                        ps_valid[li] = 1
                        if li >= ps_count:
                            ps_count = li + 1
                        ns = least_steep_slope
                    else:
                        ns = p_slope * STEEP_FACTOR
                    
                    ps_p2_idx[li] = target_idx
                    ps_p2_price[li] = highs_arr[target_idx]
                    ps_slope[li] = ns
                    ps_valid[li] = 1
                    ps_count += 1

        for li in range(ps_count):
            if ps_valid[li] == 0:
                continue
            
            # ALWAYS anchor from the LAST touch point of the purple ray
            # When purple ray gets a new touch point, move the steep line anchor forward
            if p_valid == 1 and p_last_touch_idx > ps_p1_idx[li]:
                # Purple ray has a NEW touch point ahead of our current anchor
                # Move the steep line anchor forward to this new touch point
                ps_p1_idx[li] = p_last_touch_idx
                ps_p1_price[li] = p_last_touch_price
                # Don't set slope yet - will be calculated below
            
            # Calculate the LEAST STEEP slope from anchor through all highs up to current bar
            # This ensures the line stays above all highs without being unnecessarily steep
            if i > ps_p1_idx[li]:
                least_steep_slope = -1e30
                for j in range(ps_p1_idx[li] + 1, i + 1):
                    dt = times_num[j] - times_num[ps_p1_idx[li]]
                    if dt > 0.0:
                        slope_to_j = (highs_arr[j] - ps_p1_price[li]) / dt
                        if slope_to_j >= 0.0:
                            # High went above anchor - invalidate
                            ps_valid[li] = 0
                            break
                        if slope_to_j > least_steep_slope:
                            least_steep_slope = slope_to_j
                
                if ps_valid[li] == 1 and least_steep_slope > -1e30:
                    ps_slope[li] = least_steep_slope
            
            if ps_valid[li] == 1:
                lv = ps_p1_price[li] + ps_slope[li] * (t_i - times_num[ps_p1_idx[li]])
                
                # Check if steep line is nearly horizontal (angle < 10 degrees)
                # For nearly horizontal lines, invalidate if high goes above
                price_range = highs_arr[0] - lows_arr[0]
                if price_range > 0.0:
                    angle_deg = abs(np.rad2deg(np.arctan(ps_slope[li] * (times_num[-1] - times_num[0]) / price_range)))
                    is_nearly_horizontal = angle_deg < 10.0
                else:
                    # Zero price range - treat as horizontal
                    is_nearly_horizontal = True
                
                if highs_arr[i] > lv and is_nearly_horizontal:
                    # Nearly horizontal line - invalidate immediately
                    ps_valid[li] = 0
                
                if ps_valid[li] == 1:
                    purple_steep_vals[li, i]         = lv
                    purple_steep_start_prices[li, i] = ps_p1_price[li]
                    purple_steep_p1_idxs[li, i]      = float(ps_p1_idx[li])
                    purple_steep_end_prices[li, i]   = ps_p1_price[li] + ps_slope[li] * (times_num[-1] - times_num[ps_p1_idx[li]])

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
            purple_end_prices, blue_end_prices,
            blue_steep_vals, blue_steep_start_prices, blue_steep_end_prices, blue_steep_p1_idxs,
            purple_steep_vals, purple_steep_start_prices, purple_steep_end_prices, purple_steep_p1_idxs,
            magenta_vals, magenta_slopes, lime_vals, lime_slopes_arr,
            p_anchor_p, p_p1_idx, b_anchor_p, b_p1_idx,
            o_anchor_p, o_anchor_t, y_anchor_p, y_anchor_t,
            orange_anchor_prices, orange_anchor_times,
            yellow_anchor_prices, yellow_anchor_times,
            purple_anchor_idxs, blue_anchor_idxs)


@jit(nopython=True, cache=True)
def _has_wm_shield_nb(values, shield_dist, min_touches=4):
    """Check if any price cluster within shield_dist of values[-1] exists.
    Simplified version for use inside Numba — no time span check."""
    n = len(values)
    if n < min_touches:
        return False
    ref = values[-1]
    for i in range(n):
        base = values[i]
        if abs(base - ref) > shield_dist:
            continue
        count = 0
        for j in range(n):
            if abs(values[j] - base) <= shield_dist:
                count += 1
        if count >= min_touches:
            return True
    return False


# ---------------------------------------------------------------------------
# Numba-compiled signal detection loop
# ---------------------------------------------------------------------------
# Position encoding: 0=flat, 1=long, 2=short

@jit(nopython=True, cache=False)  # cache=False to force recompile after bug fix
def _run_signals_nb(
    n, cutoff_idx,
    closes_arr, highs_arr, lows_arr, times_num,
    orange_vals, yellow_vals, purple_vals, blue_vals,
    orange_slope_val, yellow_slope_val,
    purple_slopes, blue_slopes,
    magenta_vals, magenta_slopes,
    lime_vals, lime_slopes_arr,
    purple_steep_vals, blue_steep_vals,
    x_per_unit, y_per_unit,
    pts_per_bar_visual,
    steep_angle_threshold, proximity_points,
    min_reversal_minutes, confirmation_bars,
    first_entry_steep_only,
    min_entry_angle,
    partial_tp_pts,
    wm_shield_distance,
    wm_lookback,
    spike_profit_pts,
    spike_profit_bars,
    disable_trailing_stop,
    steep_line_proximity,
    steep_line_exit_only,
    steep_line_reentry,
    num_contracts,
):
    """Pure numpy signal detection — returns parallel arrays of signals."""
    sig_type  = np.zeros(n, dtype=np.int8)
    sig_price = np.zeros(n, dtype=np.float64)
    sig_liq   = np.zeros(n, dtype=np.bool_)
    partial_tp_arr  = np.zeros(n, dtype=np.bool_)
    session_pl_arr  = np.zeros(n, dtype=np.float64)  # cumulative 2-contract P/L per bar
    pos_debug = np.zeros(n, dtype=np.int8)  # DEBUG: track position at each bar

    pos = 0  # 0=flat, 1=long, 2=short
    entry_price = 0.0
    entry_time_num = 0.0
    session_pl = 0.0
    pending_buy  = False
    pending_sell = False
    pending_ray_val = 0.0
    min_per_unit = 1.0 / (24.0 * 60.0)
    first_trade_done = False  # tracks if first trade of session has fired
    partial_taken = False     # has partial TP been taken on current trade?
    trail_anchor_p = -1e30   # locked trailing stop anchor price (v4)
    trail_anchor_t = 0.0     # locked trailing stop anchor time (v4)
    entry_time_idx = 0        # bar index of current entry
    orange_breakout = False   # price has closed above orange at least once this session
    yellow_breakout = False   # price has closed below yellow at least once this session

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

        # Track orange/yellow breakouts — once price closes outside, give trend more weight
        if close > orange_vals[i]: orange_breakout = True
        if close < yellow_vals[i]: yellow_breakout = True

        # --- Partial take-profit (1 of 2 contracts at partial_tp_pts) ---
        if (partial_tp_pts > 0.0 and pos != 0 and not partial_taken
                and entry_price != 0.0):
            unrealized = (close - entry_price) if pos == 1 else (entry_price - close)
            if unrealized >= partial_tp_pts:
                session_pl += unrealized  # book 1 contract
                partial_taken = True
                partial_tp_arr[i] = True  # flag this bar for order placement

        # --- Spike profit exit: if unrealized >= spike_profit_pts within spike_profit_bars ---
        if (spike_profit_pts > 0.0 and pos != 0 and entry_price != 0.0
                and not liquidated and (i - entry_time_idx) <= spike_profit_bars
                and (i - entry_time_idx) > 0):
            unrealized = (close - entry_price) if pos == 1 else (entry_price - close)
            if unrealized >= spike_profit_pts:
                contracts_remaining = 1 if partial_taken else num_contracts
                session_pl += unrealized * contracts_remaining
                sig_type[i] = 2 if pos == 1 else 1
                sig_price[i] = close
                sig_liq[i] = True
                pos = 0; entry_price = 0.0; entry_time_num = 0.0
                trail_anchor_p = -1e30; trail_anchor_t = 0.0
                entry_time_idx = 0; liquidated = True
                partial_taken = False

        # --- Trailing stop v4 ---
        # threshold=50pts, angles=50/60/70, anchor locked once set
        if pos != 0 and i >= 5 and disable_trailing_stop == 0:
            unrealized = (close - entry_price) if pos == 1 else (entry_price - close)
            if unrealized >= 50.0:
                # Determine angle based on profit level
                if unrealized >= 150.0:
                    trail_angle = 70.0
                elif unrealized >= 100.0:
                    trail_angle = 60.0
                else:
                    trail_angle = 50.0
                trailing_slope = np.tan(np.deg2rad(trail_angle)) * (y_per_unit / x_per_unit)

                # Use locked anchor if already set, otherwise find and lock it
                if trail_anchor_p < -1e29:
                    # Search for swing anchor point
                    start_j = max(entry_time_idx, i - 15)
                    if pos == 1:
                        best_lo = -1e30
                        for j in range(start_j, i):
                            if j == 0 or j >= n - 1: continue
                            lo = lows_arr[j]
                            if lows_arr[j-1] - lo >= 10.0 and lows_arr[j+1] - lo >= 10.0:
                                if lo > best_lo:
                                    best_lo = lo
                                    trail_anchor_p = lo
                                    trail_anchor_t = times_num[j]
                        if trail_anchor_p < -1e29:
                            trail_anchor_p = lows_arr[entry_time_idx]
                            trail_anchor_t = times_num[entry_time_idx]
                    else:
                        best_hi = 1e30
                        for j in range(start_j, i):
                            if j == 0 or j >= n - 1: continue
                            hi = highs_arr[j]
                            if hi - highs_arr[j-1] >= 10.0 and hi - highs_arr[j+1] >= 10.0:
                                if hi < best_hi:
                                    best_hi = hi
                                    trail_anchor_p = hi
                                    trail_anchor_t = times_num[j]
                        if trail_anchor_p > 1e29:
                            trail_anchor_p = highs_arr[entry_time_idx]
                            trail_anchor_t = times_num[entry_time_idx]

                # Check if close crosses trailing line
                if trail_anchor_t > 0.0:
                    t_diff = times_num[i] - trail_anchor_t
                    if t_diff > 0.0:
                        if pos == 1:
                            if close < trail_anchor_p + trailing_slope * t_diff:
                                # Suppress if close is within steep_line_proximity of original blue ray
                                _bl = blue_vals[i]
                                if steep_line_proximity > 0.0 and not np.isnan(_bl) and abs(close - _bl) <= steep_line_proximity:
                                    pass  # near original blue — hold long
                                else:
                                    contracts_remaining = 1 if partial_taken else num_contracts
                                    session_pl += (close - entry_price) * contracts_remaining
                                    sig_type[i] = 2; sig_price[i] = close; sig_liq[i] = True
                                    pos = 0; entry_price = 0.0; entry_time_num = 0.0
                                    trail_anchor_p = -1e30; trail_anchor_t = 0.0
                                    entry_time_idx = 0; liquidated = True
                                    partial_taken = False
                        else:
                            if close > trail_anchor_p - trailing_slope * t_diff:
                                # Suppress if close is within steep_line_proximity of original purple ray
                                _pu = purple_vals[i]
                                if steep_line_proximity > 0.0 and not np.isnan(_pu) and abs(close - _pu) <= steep_line_proximity:
                                    pass  # near original purple — hold short
                                else:
                                    contracts_remaining = 1 if partial_taken else num_contracts
                                    session_pl += (entry_price - close) * contracts_remaining
                                    sig_type[i] = 1; sig_price[i] = close; sig_liq[i] = True
                                    pos = 0; entry_price = 0.0; entry_time_num = 0.0
                                    trail_anchor_p = -1e30; trail_anchor_t = 0.0
                                    entry_time_idx = 0; liquidated = True
                                    partial_taken = False

        # --- Steeper line reversal ---
        # Steep purple = descending resistance above price (relevant when SHORT)
        #   Close crosses ABOVE steep purple -> price broke out up -> reverse short->long
        # Steep blue = ascending support below price (relevant when LONG)
        #   Close crosses BELOW steep blue -> price broke down -> reverse long->short
        # Only fire if held position for at least 2 bars
        if not liquidated and pos != 0 and (i - entry_time_idx) >= 2:
            if pos == 2:
                # Short: steep purple above us, cross above = reverse to long (or exit if steep_line_exit_only)
                # Suppress if close is within steep_line_proximity pts of original purple ray
                curr_purple = purple_vals[i]
                for li in range(purple_steep_vals.shape[0]):
                    pv_prev = purple_steep_vals[li, i - 1]
                    pv_curr = purple_steep_vals[li, i]
                    if np.isnan(pv_prev) or np.isnan(pv_curr):
                        continue
                    if closes_arr[i - 1] <= pv_prev and closes_arr[i] > pv_curr:
                        if steep_line_proximity > 0.0 and not np.isnan(curr_purple) and abs(closes_arr[i] - curr_purple) <= steep_line_proximity:
                            break  # too close to original purple — hold short
                        contracts_remaining = 1 if partial_taken else num_contracts
                        session_pl += (entry_price - closes_arr[i]) * contracts_remaining
                        sig_type[i] = 1 if not steep_line_exit_only else 0  # BUY or EXIT
                        sig_price[i] = closes_arr[i]
                        sig_liq[i] = False
                        if steep_line_exit_only:
                            pos = 0  # exit to flat
                        else:
                            pos = 1  # reverse to long
                            entry_price = closes_arr[i]
                            entry_time_num = times_num[i]
                            entry_time_idx = i
                            trail_anchor_p = -1e30
                            trail_anchor_t = 0.0
                            orange_breakout = False
                            yellow_breakout = False
                        partial_taken = False
                        first_trade_done = True
                        liquidated = True
                        break
            elif pos == 1:
                # Long: steep blue below us, cross below = reverse to short (or exit if steep_line_exit_only)
                # Suppress if close is within steep_line_proximity pts of original blue ray
                curr_blue = blue_vals[i]
                for li in range(blue_steep_vals.shape[0]):
                    bv_prev = blue_steep_vals[li, i - 1]
                    bv_curr = blue_steep_vals[li, i]
                    if np.isnan(bv_prev) or np.isnan(bv_curr):
                        continue
                    if closes_arr[i - 1] >= bv_prev and closes_arr[i] < bv_curr:
                        if steep_line_proximity > 0.0 and not np.isnan(curr_blue) and abs(closes_arr[i] - curr_blue) <= steep_line_proximity:
                            break  # too close to original blue — hold long
                        contracts_remaining = 1 if partial_taken else num_contracts
                        session_pl += (closes_arr[i] - entry_price) * contracts_remaining
                        sig_type[i] = 2 if not steep_line_exit_only else 0  # SELL or EXIT
                        sig_price[i] = closes_arr[i]
                        sig_liq[i] = False
                        if steep_line_exit_only:
                            pos = 0  # exit to flat
                        else:
                            pos = 2  # reverse to short
                            entry_price = closes_arr[i]
                            entry_time_num = times_num[i]
                            entry_time_idx = i
                            trail_anchor_p = -1e30
                            trail_anchor_t = 0.0
                            orange_breakout = False
                            yellow_breakout = False
                        partial_taken = False
                        first_trade_done = True
                        liquidated = True
                        break

        # Reversal guard
        mins_since = (times_num[i] - entry_time_num) / min_per_unit if entry_time_num > 0.0 else 9999.0
        orange_cross_buy  = prev_close <= prev_orange and close > prev_orange
        yellow_cross_sell = prev_close >= prev_yellow and close < prev_yellow
        safety_override   = (pos == 2 and orange_cross_buy) or (pos == 1 and yellow_cross_sell)
        reversal_blocked  = min_reversal_minutes > 0 and mins_since < min_reversal_minutes and not safety_override

        # Orange/yellow breakout patience:
        # If orange breakout occurred THIS trade, long positions only reverse on yellow cross (not purple/blue)
        # If yellow breakout occurred THIS trade, short positions only reverse on orange cross (not purple/blue)
        breakout_patience_buy  = False
        breakout_patience_sell = False

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
            elif pos == 2 and breakout_patience_buy:
                pending_buy = False  # yellow breakout active — only reverse on orange cross
            else:
                # Water mark shield: suppress reversal if cluster supports short position
                wm_shielded = False
                if wm_shield_distance > 0.0 and pos == 2 and i >= wm_lookback:
                    ws = max(0, i - wm_lookback)
                    wm_shielded = _has_wm_shield_nb(highs_arr[ws:i], wm_shield_distance)

                if wm_shielded:
                    pass  # hold short — cluster is shielding
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
                            # For first trade, purple angle must be >= min_entry_angle
                            purple_angle_ready = pa >= min_entry_angle if (min_entry_angle > 0.0 and not first_trade_done) else True
                            if pa < steep_angle_threshold and purple_angle_ready and prev_close <= prev_purple and close > prev_purple:
                                if abs(close - curr_orange) > proximity_points:
                                    buy_triggered = True
                        if not buy_triggered and i > 0 and not np.isnan(magenta_vals[i-1]):
                            pm = magenta_vals[i-1]; ms = magenta_slopes[i-1]
                            ma = abs(np.rad2deg(np.arctan(abs(ms) * x_per_unit / y_per_unit))) if not np.isnan(ms) else 999.0
                            if ma < steep_angle_threshold and prev_close <= pm and close > pm:
                                if abs(close - curr_orange) > proximity_points:
                                    buy_triggered = True
                        # Steep line re-entry: when flat after first trade, cross above steep purple = BUY
                        if not buy_triggered and steep_line_reentry and pos == 0 and first_trade_done:
                            for li in range(purple_steep_vals.shape[0]):
                                pv_prev = purple_steep_vals[li, i - 1]
                                pv_curr = purple_steep_vals[li, i]
                                if np.isnan(pv_prev) or np.isnan(pv_curr):
                                    continue
                                if prev_close <= pv_prev and close > pv_curr:
                                    _pu = purple_vals[i]
                                    if steep_line_proximity > 0.0 and not np.isnan(_pu) and abs(close - _pu) <= steep_line_proximity:
                                        break  # too close to original purple — skip
                                    buy_triggered = True
                                    break
                    if buy_triggered:
                        # BUG FIX: Defensive check to prevent duplicate BUY when already LONG
                        if pos == 1:
                            pass  # Already LONG - ignore duplicate BUY signal
                        else:
                            if pos == 2:
                                contracts_remaining = 1 if partial_taken else num_contracts
                                session_pl += (entry_price - close) * contracts_remaining
                            sig_type[i] = 1; sig_price[i] = close  # Record BUY signal
                            if is_last: pos = 0; entry_price = 0.0; entry_time_num = 0.0
                            else: pos = 1; entry_price = close; entry_time_num = times_num[i]; entry_time_idx = i; first_trade_done = True; partial_taken = False; trail_anchor_p = -1e30; trail_anchor_t = 0.0
                            orange_breakout = False; yellow_breakout = False

        # --- SELL signals ---
        if pos != 2 and sig_type[i] == 0 and not liquidated and angle_ready:
            if pos == 1 and reversal_blocked:
                pending_sell = False
            elif pos == 1 and breakout_patience_sell:
                pending_sell = False  # orange breakout active — only reverse on yellow cross
            else:
                # Water mark shield: suppress reversal if cluster supports long position
                wm_shielded = False
                if wm_shield_distance > 0.0 and pos == 1 and i >= wm_lookback:
                    ws = max(0, i - wm_lookback)
                    wm_shielded = _has_wm_shield_nb(lows_arr[ws:i], wm_shield_distance)

                if wm_shielded:
                    pass  # hold long — cluster is shielding
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
                        # Steep line re-entry: when flat after first trade, cross below steep blue = SELL
                        if not sell_triggered and steep_line_reentry and pos == 0 and first_trade_done:
                            for li in range(blue_steep_vals.shape[0]):
                                bv_prev = blue_steep_vals[li, i - 1]
                                bv_curr = blue_steep_vals[li, i]
                                if np.isnan(bv_prev) or np.isnan(bv_curr):
                                    continue
                                if prev_close >= bv_prev and close < bv_curr:
                                    _bl = blue_vals[i]
                                    if steep_line_proximity > 0.0 and not np.isnan(_bl) and abs(close - _bl) <= steep_line_proximity:
                                        break  # too close to original blue — skip
                                    sell_triggered = True
                                    break
                    if sell_triggered:
                        # BUG FIX: Defensive check to prevent duplicate SELL when already SHORT
                        if pos == 2:
                            # DEBUG: Log when we skip duplicate SELL
                            # print(f"SKIPPED duplicate SELL at bar {i}, already short")
                            pass  # Already SHORT - ignore duplicate SELL signal
                        else:
                            if pos == 1:
                                contracts_remaining = 1 if partial_taken else num_contracts
                                session_pl += (close - entry_price) * contracts_remaining
                            sig_type[i] = 2; sig_price[i] = close  # Only record signal when actually acting
                            if is_last: pos = 0; entry_price = 0.0; entry_time_num = 0.0
                            else: pos = 2; entry_price = close; entry_time_num = times_num[i]; entry_time_idx = i; first_trade_done = True; partial_taken = False; trail_anchor_p = -1e30; trail_anchor_t = 0.0
                            orange_breakout = False; yellow_breakout = False

        # Track cumulative 2-contract P/L (realized + unrealized on contract 2)
        if pos == 0 or entry_price == 0.0:
            session_pl_arr[i] = session_pl
        elif pos == 1:
            session_pl_arr[i] = session_pl + (closes_arr[i] - entry_price)
        else:
            session_pl_arr[i] = session_pl + (entry_price - closes_arr[i])
        
        pos_debug[i] = pos  # DEBUG: track position at end of each bar

    return sig_type, sig_price, sig_liq, partial_tp_arr, session_pl_arr, pos_debug


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

    full_data = data
    est = pytz.timezone("US/Eastern")
    try:
        if full_data.index.tz is None:
            full_data = data.copy()
            full_data.index = pd.to_datetime(full_data.index, errors="coerce").tz_localize(est)
        else:
            full_data = data  # already tz-aware, no copy needed
            full_data.index = pd.to_datetime(full_data.index).tz_convert(est)
    except:
        full_data = data.copy()

    cfg = config or AlgoConfig()
    n = len(full_data)

    # Hard cutoff times — no trading before start_time + warmup_minutes.
    # Day session:   starts 9:30, default warmup 12 min → first signal at 9:42 ET
    # Night session: starts 3:00 AM, default warmup 12 min → first signal at 3:12 AM ET
    _is_night = start_time >= "18:00" or start_time <= "09:00"
    _warmup = cfg.warmup_minutes if cfg.warmup_minutes is not None else 12
    if _is_night:
        cutoff_time = pd.Timestamp(f"{target_date} {start_time}:00", tz=est) + pd.Timedelta(minutes=_warmup)
    else:
        cutoff_time = pd.Timestamp(f"{target_date} {start_time}:00", tz=est) + pd.Timedelta(minutes=_warmup)

    # --- Extract numpy arrays ONCE ---
    highs_arr  = full_data["High"].values.astype(np.float64)
    lows_arr   = full_data["Low"].values.astype(np.float64)
    closes_arr = full_data["Close"].values.astype(np.float64)
    times_idx  = full_data.index
    # Fast vectorized conversion: pandas timestamps → matplotlib date numbers
    times_num  = full_data.index.asi8 / 8.64e10 + 719163.0  # µs since epoch → matplotlib datenum

    # Aspect ratio — match original TradingAlgo.py exactly
    _ax_w_in = 16.0 * (0.85 - 0.125)
    _ax_h_in = 9.0 * (0.88 - 0.11)
    _x_range = 75 / (24 * 60)
    _y_range = highs_arr.max() + 20.0 - (lows_arr.min() - 20.0)
    x_per_unit = _x_range / _ax_w_in
    y_per_unit = _y_range / _ax_h_in

    # Find cutoff index
    cutoff_idx = n  # Default to end of data if cutoff time not reached yet
    for i in range(n):
        if times_idx[i] >= cutoff_time:
            cutoff_idx = i
            break

    # --- Compute ALL rays via Numba ---
    orange_slope_val = -np.tan(np.deg2rad(cfg.orange_angle)) * (y_per_unit / x_per_unit)
    yellow_slope_val =  np.tan(np.deg2rad(cfg.yellow_angle)) * (y_per_unit / x_per_unit)

    (orange_vals, yellow_vals, purple_vals, blue_vals,
     purple_slopes, blue_slopes, purple_start_prices, blue_start_prices,
     purple_end_prices, blue_end_prices,
     blue_steep_vals, blue_steep_start_prices, blue_steep_end_prices, blue_steep_p1_idxs,
     purple_steep_vals, purple_steep_start_prices, purple_steep_end_prices, purple_steep_p1_idxs,
     magenta_vals, magenta_slopes, lime_vals, lime_slopes_arr,
     p_anchor_p, p_anchor_idx, b_anchor_p, b_anchor_idx,
     o_anchor_p, o_anchor_t, y_anchor_p, y_anchor_t,
     orange_anchor_prices, orange_anchor_times,
     yellow_anchor_prices, yellow_anchor_times,
     purple_anchor_idxs, blue_anchor_idxs) = _compute_rays_nb(
        n, highs_arr, lows_arr, closes_arr, times_num,
        orange_slope_val, yellow_slope_val,
        cutoff_idx, cfg.steep_line_threshold,
        1 if cfg.reanchor_blue_purple else 0,
        cfg.reanchor_min_bars,
        cfg.reanchor_swing_threshold,
    )
    # pts_per_bar_visual: how many price points = 1 bar width on the chart (for angle calc)
    # 75 bars visible on the standard chart window
    pts_per_bar_visual = _y_range / 75.0

    # --- Signal detection — Numba compiled ---
    sig_type, sig_price, sig_liq, partial_tp_arr, session_pl_arr, pos_debug = _run_signals_nb(
        n, cutoff_idx,
        closes_arr, highs_arr, lows_arr, times_num,
        orange_vals, yellow_vals, purple_vals, blue_vals,
        orange_slope_val, yellow_slope_val,
        purple_slopes, blue_slopes,
        magenta_vals, magenta_slopes,
        lime_vals, lime_slopes_arr,
        purple_steep_vals, blue_steep_vals,
        x_per_unit, y_per_unit,
        pts_per_bar_visual,
        cfg.steep_angle_threshold, cfg.proximity_points,
        cfg.min_reversal_minutes, cfg.confirmation_bars,
        1 if cfg.first_entry_steep_only else 0,
        cfg.min_entry_angle,
        cfg.partial_tp_pts,
        cfg.wm_shield_distance,
        cfg.wm_lookback,
        cfg.spike_profit_pts,
        cfg.spike_profit_bars,
        1 if cfg.disable_trailing_stop else 0,
        cfg.steep_line_proximity,
        1 if cfg.steep_line_exit_only else 0,
        1 if cfg.steep_line_reentry else 0,
        cfg.num_contracts,
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
    result["session_pl"] = session_pl_arr  # cumulative 2-contract P/L, bar by bar
    result["pos_debug"] = pos_debug  # DEBUG: position at each bar (0=flat, 1=long, 2=short)


    result["orange_ray"] = orange_vals
    result["partial_tp"] = partial_tp_arr  # True on bars where partial TP fired
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

    # Ray start/end — matches original April 23 approach exactly
    result["orange_ray_start_price"] = orange_anchor_prices
    result["orange_ray_start_time"]  = [times_idx[int(orange_anchor_times[i])] for i in range(n)]
    result["yellow_ray_start_price"] = yellow_anchor_prices
    result["yellow_ray_start_time"]  = [times_idx[int(yellow_anchor_times[i])] for i in range(n)]
    result["purple_ray_start_price"] = purple_start_prices
    result["purple_ray_start_time"]  = [times_idx[int(purple_anchor_idxs[i])] for i in range(n)]
    result["blue_ray_start_price"]   = blue_start_prices
    result["blue_ray_start_time"]    = [times_idx[int(blue_anchor_idxs[i])] for i in range(n)]

    result["orange_angle"] = _display_angle_from_slope(orange_slope_val, x_per_unit, y_per_unit)
    result["yellow_angle"] = _display_angle_from_slope(yellow_slope_val, x_per_unit, y_per_unit)
    result["purple_angle"] = [_display_angle_from_slope(s, x_per_unit, y_per_unit) for s in purple_slopes]
    result["blue_angle"]   = [_display_angle_from_slope(s, x_per_unit, y_per_unit) for s in blue_slopes]

    # End prices: project from bar-0 anchor using fixed slope to session end
    _dt_full = times_num[-1] - times_num[0]
    result["orange_ray_end_price"] = [
        float(orange_anchor_prices[i]) + orange_slope_val * (times_num[-1] - times_num[int(orange_anchor_times[i])])
        for i in range(n)]
    result["yellow_ray_end_price"] = [
        float(yellow_anchor_prices[i]) + yellow_slope_val * (times_num[-1] - times_num[int(yellow_anchor_times[i])])
        for i in range(n)]
    # Purple/blue end: pre-computed in Numba, projected to session end
    result["purple_ray_end_price"] = purple_end_prices
    result["blue_ray_end_price"]   = blue_end_prices

    # Steeper blue/purple family (up to 4 each)
    for li in range(4):
        result[f"blue_steep_{li}_vals"]         = blue_steep_vals[li, :]
        result[f"blue_steep_{li}_start_prices"] = blue_steep_start_prices[li, :]
        result[f"blue_steep_{li}_end_prices"]   = blue_steep_end_prices[li, :]
        result[f"blue_steep_{li}_p1_idxs"]      = blue_steep_p1_idxs[li, :]
        result[f"purple_steep_{li}_vals"]         = purple_steep_vals[li, :]
        result[f"purple_steep_{li}_start_prices"] = purple_steep_start_prices[li, :]
        result[f"purple_steep_{li}_end_prices"]   = purple_steep_end_prices[li, :]
        result[f"purple_steep_{li}_p1_idxs"]      = purple_steep_p1_idxs[li, :]

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
