"""
_sweep_trailing.py
------------------
Sweeps trailing stop parameters across 667 days (9:30-17:00).

Tests:
  - activation threshold (pts of unrealized profit before trailing activates)
  - trail angle (degrees)
  - anchor locking (re-anchor every bar vs lock once set)
  - progressive angle tightening

Baseline: no trailing stop (just run to session end)
Current v3: threshold=75, angles=40/50/60, re-anchor every bar

Run: python _sweep_trailing.py
"""

import os, glob
import pandas as pd
import numpy as np
import pytz
import matplotlib.dates as mdates
from multiprocessing import Pool, cpu_count
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig

_EST       = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.expanduser("~/Desktop/2YearsData/full_day")

# Base config — no trailing stop (we apply it post-hoc in this sweep)
BASE_CONFIG = AlgoConfig(
    warmup_minutes=12,
    steep_angle_threshold=70.0,
    proximity_points=15.0,
    min_reversal_minutes=0,
    min_entry_angle=30.0,
    partial_tp_pts=50.0,
    # disable built-in trailing by setting threshold very high
    spike_profit_pts=99999.0,
)

# ─────────────────────────────────────────────────────────────────────────────
# Post-hoc trailing stop calculator
# ─────────────────────────────────────────────────────────────────────────────
def _apply_trailing(algo_df, start_ts, end_ts,
                    threshold=75.0,
                    base_angle=40.0,
                    mid_angle=50.0,
                    high_angle=60.0,
                    mid_profit=100.0,
                    high_profit=150.0,
                    lock_anchor=False,
                    progressive=False):
    """
    Apply trailing stop post-hoc to algo signals.
    threshold    : unrealized pts before trailing activates
    base_angle   : angle when no confirmed swing
    mid_angle    : angle when swing confirmed
    high_angle   : angle when swing confirmed + high_profit reached
    lock_anchor  : if True, anchor is locked once set (not re-searched every bar)
    progressive  : if True, angle increases 5° every 10 bars held
    """
    sliced = algo_df[(algo_df.index >= start_ts) & (algo_df.index <= end_ts)]
    if len(sliced) < 2:
        return None

    # Aspect ratio (same as TradingAlgoFast)
    highs  = sliced["High"].values.astype(np.float64)
    lows   = sliced["Low"].values.astype(np.float64)
    closes = sliced["Close"].values.astype(np.float64)
    times  = sliced.index

    _ax_w_in = 16.0 * (0.85 - 0.125)
    _ax_h_in = 9.0  * (0.88 - 0.11)
    _x_range = 75 / (24 * 60)
    _y_range = highs.max() + 20.0 - (lows.min() - 20.0)
    x_per_unit = _x_range / _ax_w_in
    y_per_unit = _y_range / _ax_h_in
    times_num  = np.array([mdates.date2num(t) for t in times])
    min_per_unit = 1.0 / (24 * 60) / x_per_unit

    # Get raw signals (before trailing)
    raw_sigs = sliced[sliced["signal"].isin(["BUY", "SELL"])]
    if raw_sigs.empty:
        return None

    signal_list = [(ts, row["signal"],
                    float(row["buy_price"] if row["signal"] == "BUY" else row["sell_price"]))
                   for ts, row in raw_sigs.iterrows()]

    tpls = []
    pos, ep, entry_bar = "flat", None, 0
    partial_taken = False
    PARTIAL_TP = 50.0
    sig_idx = 0

    # Anchor state for locked mode
    locked_anchor_p = None
    locked_anchor_t = None

    for i in range(len(sliced)):
        close = closes[i]

        # Partial TP
        if PARTIAL_TP > 0 and pos != "flat" and ep is not None and not partial_taken:
            unreal = (close - ep) if pos == "long" else (ep - close)
            if unreal >= PARTIAL_TP:
                tpls.append(unreal)
                partial_taken = True

        # Check raw signal
        if sig_idx < len(signal_list) and times[i] == signal_list[sig_idx][0]:
            ts, sig, price = signal_list[sig_idx]; sig_idx += 1
            if pos == "long" and sig == "SELL":
                tpls.append(price - ep)
                pos, ep, entry_bar = "short", price, i
                partial_taken = False
                locked_anchor_p = locked_anchor_t = None
            elif pos == "short" and sig == "BUY":
                tpls.append(ep - price)
                pos, ep, entry_bar = "long", price, i
                partial_taken = False
                locked_anchor_p = locked_anchor_t = None
            elif pos == "flat":
                pos = "long" if sig == "BUY" else "short"
                ep = price; entry_bar = i
                locked_anchor_p = locked_anchor_t = None
            continue

        # Trailing stop
        if pos != "flat" and ep is not None and i >= entry_bar + 2:
            unreal = (close - ep) if pos == "long" else (ep - close)
            if unreal >= threshold:
                bars_held = i - entry_bar

                # Determine angle
                if progressive:
                    angle = base_angle + 5.0 * (bars_held // 10)
                    angle = min(angle, 75.0)
                else:
                    if unreal >= high_profit:
                        angle = high_angle
                    elif unreal >= mid_profit:
                        angle = mid_angle
                    else:
                        angle = base_angle

                trail_slope = np.tan(np.deg2rad(angle)) * (y_per_unit / x_per_unit)

                # Find anchor
                if lock_anchor and locked_anchor_p is not None:
                    anchor_p = locked_anchor_p
                    anchor_t = locked_anchor_t
                else:
                    # Search for swing point
                    anchor_p = None; anchor_t = None
                    start_j = max(entry_bar, i - 15)
                    if pos == "long":
                        best_lo = -1e30
                        for k in range(start_j, i):
                            if k == 0 or k >= len(lows) - 1: continue
                            lo = lows[k]
                            if lows[k-1] - lo >= 10.0 and lows[k+1] - lo >= 10.0:
                                if lo > best_lo:
                                    best_lo = lo; anchor_p = lo; anchor_t = times_num[k]
                        if anchor_p is None:
                            anchor_p = lows[entry_bar]; anchor_t = times_num[entry_bar]
                    else:
                        best_hi = 1e30
                        for k in range(start_j, i):
                            if k == 0 or k >= len(highs) - 1: continue
                            hi = highs[k]
                            if hi - highs[k-1] >= 10.0 and hi - highs[k+1] >= 10.0:
                                if hi < best_hi:
                                    best_hi = hi; anchor_p = hi; anchor_t = times_num[k]
                        if anchor_p is None:
                            anchor_p = highs[entry_bar]; anchor_t = times_num[entry_bar]

                    if lock_anchor:
                        locked_anchor_p = anchor_p
                        locked_anchor_t = anchor_t

                # Check if close crosses trailing line
                if anchor_p is not None and anchor_t is not None:
                    t_diff = times_num[i] - anchor_t
                    if t_diff > 0:
                        if pos == "long":
                            trail_val = anchor_p + trail_slope * t_diff
                            if close < trail_val:
                                tpls.append(close - ep)
                                pos, ep, entry_bar = "flat", None, 0
                                partial_taken = False
                                locked_anchor_p = locked_anchor_t = None
                        else:
                            trail_val = anchor_p - trail_slope * t_diff
                            if close > trail_val:
                                tpls.append(ep - close)
                                pos, ep, entry_bar = "flat", None, 0
                                partial_taken = False
                                locked_anchor_p = locked_anchor_t = None

    # Close open position at end
    if pos != "flat" and ep is not None:
        tpls.append((closes[-1] - ep) if pos == "long" else (ep - closes[-1]))

    return sum(tpls) if tpls else None


# ─────────────────────────────────────────────────────────────────────────────
# Scenarios
# ─────────────────────────────────────────────────────────────────────────────
SCENARIOS = {}

def _build_scenarios():
    global SCENARIOS

    # Baseline — no trailing stop (hold to session end)
    SCENARIOS["baseline_no_trail"] = dict(threshold=99999)

    # Current v3 equivalent
    SCENARIOS["v3_current"] = dict(threshold=75, base_angle=40, mid_angle=50,
                                   high_angle=60, mid_profit=100, high_profit=150,
                                   lock_anchor=False, progressive=False)

    # Threshold sweep (with v3 angles, no lock)
    for t in [25, 50, 75, 100, 125, 150]:
        SCENARIOS[f"thresh_{t}"] = dict(threshold=t, base_angle=40, mid_angle=50,
                                        high_angle=60, mid_profit=100, high_profit=150,
                                        lock_anchor=False, progressive=False)

    # Angle sweep (threshold=75, no lock)
    for base in [30, 40, 50, 60]:
        for high in [50, 60, 70]:
            if high <= base: continue
            SCENARIOS[f"ang_{base}_{high}"] = dict(threshold=75, base_angle=base,
                                                    mid_angle=(base+high)//2,
                                                    high_angle=high, mid_profit=100,
                                                    high_profit=150, lock_anchor=False,
                                                    progressive=False)

    # Lock anchor sweep
    for t in [50, 75, 100]:
        SCENARIOS[f"lock_{t}"] = dict(threshold=t, base_angle=40, mid_angle=50,
                                      high_angle=60, mid_profit=100, high_profit=150,
                                      lock_anchor=True, progressive=False)

    # Progressive angle
    for t in [50, 75, 100]:
        SCENARIOS[f"prog_{t}"] = dict(threshold=t, base_angle=30, mid_angle=50,
                                      high_angle=60, mid_profit=100, high_profit=150,
                                      lock_anchor=False, progressive=True)

    # Best combos: lock + progressive
    for t in [50, 75]:
        SCENARIOS[f"lock_prog_{t}"] = dict(threshold=t, base_angle=30, mid_angle=50,
                                           high_angle=70, mid_profit=100, high_profit=150,
                                           lock_anchor=True, progressive=True)

_build_scenarios()


def _process_file(fpath):
    d = os.path.basename(fpath).replace("CBOT_MINI_YM1_", "").replace(".csv", "")
    try:
        df = pd.read_csv(fpath, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        start_ts = pd.Timestamp(f"{d} 09:30", tz=_EST)
        end_ts   = pd.Timestamp(f"{d} 17:00", tz=_EST)
        day_data = df[(df.index >= start_ts) & (df.index <= end_ts)]
        if len(day_data) < 15:
            return None
        algo_df = run_trading_algo_fast(day_data, d, "09:30", "17:00", config=BASE_CONFIG)
        row = {"date": d}
        for name, kwargs in SCENARIOS.items():
            result = _apply_trailing(algo_df, start_ts, end_ts, **kwargs)
            row[name] = result if result is not None else 0.0
        return row
    except Exception:
        return None


def main():
    files = sorted(glob.glob(os.path.join(_DATA_ROOT, "CBOT_MINI_YM1_*.csv")))
    print(f"Processing {len(files)} days with {len(SCENARIOS)} scenarios ...")

    with Pool(max(1, cpu_count() - 1)) as pool:
        results = pool.map(_process_file, files)

    results = [r for r in results if r is not None]
    df = pd.DataFrame(results).set_index("date")

    summary = pd.DataFrame({
        "total_pts": df.sum(),
        "avg_pts":   df.mean(),
        "win_days":  (df > 0).sum(),
        "lose_days": (df < 0).sum(),
    })
    summary["win_pct"] = (summary["win_days"] / (summary["win_days"] + summary["lose_days"]) * 100).round(1)
    summary = summary.sort_values("total_pts", ascending=False)

    pd.set_option("display.width", 200)
    print("\n" + "=" * 90)
    print(f"{'Scenario':<25} {'Total Pts':>10} {'Avg/Day':>9} {'Win%':>6} {'WinDays':>8} {'LoseDays':>9}")
    print("=" * 90)
    for name, row in summary.iterrows():
        marker = " <-- BASELINE" if name == "baseline_no_trail" else (" <-- V3 CURRENT" if name == "v3_current" else "")
        print(f"{name:<25} {row['total_pts']:>10.0f} {row['avg_pts']:>9.1f} {row['win_pct']:>6.1f}%"
              f" {row['win_days']:>8.0f} {row['lose_days']:>9.0f}{marker}")

    df.to_csv("_sweep_trailing_results.csv")
    summary.to_csv("_sweep_trailing_summary.csv")
    print(f"\nSaved to _sweep_trailing_results.csv / _sweep_trailing_summary.csv")


if __name__ == "__main__":
    main()
