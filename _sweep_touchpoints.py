"""
_sweep_touchpoints.py
---------------------
Tests trendline touch-point validation on blue/purple ray crosses.

Idea: before firing a BUY on blue ray cross or SELL on purple ray cross,
require the ray to have been "tested" N times (price came close, then bounced away).

A valid touch requires:
  1. Price came within `touch_proximity` pts of the ray
  2. Price then moved away at least `min_bounce` pts before returning
  3. At least `min_bars_gap` bars since the last touch

Sweeps: min_touches (2,3,4), touch_proximity (5,10,15,20), min_bounce (20,30,50), min_bars_gap (3,5,10)

Baseline: no touch filter (current behavior)

Run: python _sweep_touchpoints.py
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

BASE_CONFIG = AlgoConfig(
    warmup_minutes=12,
    steep_angle_threshold=70.0,
    proximity_points=15.0,
    min_reversal_minutes=0,
    min_entry_angle=30.0,
    partial_tp_pts=50.0,
)

PARTIAL_TP = 50.0


# ─────────────────────────────────────────────────────────────────────────────
# Touch point counter
# ─────────────────────────────────────────────────────────────────────────────
def _count_touches(lows, highs, closes, ray_vals, direction,
                   touch_proximity, min_bounce, min_bars_gap, up_to_bar):
    """
    Count validated touch points on a ray up to bar index `up_to_bar`.

    direction: 'up' = blue ray (support, check lows)
               'down' = purple ray (resistance, check highs)

    Returns number of validated touches.
    """
    touches = 0
    last_touch_bar = -999
    last_touch_price = None
    in_bounce = False
    bounce_extreme = None

    for i in range(up_to_bar + 1):
        ray = ray_vals[i]
        if ray <= 0:
            continue

        if direction == 'up':
            # Blue ray support — check if low came close
            dist = lows[i] - ray  # positive = above ray, negative = below
            price_ref = lows[i]
            bounce_ref = highs[i]
        else:
            # Purple ray resistance — check if high came close
            dist = ray - highs[i]  # positive = below ray, negative = above
            price_ref = highs[i]
            bounce_ref = lows[i]

        near_ray = abs(dist) <= touch_proximity and dist >= -touch_proximity

        if near_ray and (i - last_touch_bar) >= min_bars_gap:
            # Potential touch — check if previous touch had a valid bounce
            if last_touch_price is None:
                # First touch — always count it
                touches += 1
                last_touch_bar = i
                last_touch_price = price_ref
                bounce_extreme = bounce_ref
                in_bounce = False
            else:
                # Need to verify bounce happened since last touch
                if direction == 'up':
                    bounced = (bounce_extreme is not None and
                               bounce_extreme - last_touch_price >= min_bounce)
                else:
                    bounced = (bounce_extreme is not None and
                               last_touch_price - bounce_extreme >= min_bounce)

                if bounced:
                    touches += 1
                    last_touch_bar = i
                    last_touch_price = price_ref
                    bounce_extreme = bounce_ref
                    in_bounce = False
        else:
            # Track bounce extreme between touches
            if last_touch_price is not None:
                if direction == 'up':
                    if bounce_extreme is None or highs[i] > bounce_extreme:
                        bounce_extreme = highs[i]
                else:
                    if bounce_extreme is None or lows[i] < bounce_extreme:
                        bounce_extreme = lows[i]

    return touches


# ─────────────────────────────────────────────────────────────────────────────
# P&L calculator with touch filter
# ─────────────────────────────────────────────────────────────────────────────
def calc_pl_with_touches(algo_df, start_ts, end_ts,
                         min_touches=2,
                         touch_proximity=10.0,
                         min_bounce=30.0,
                         min_bars_gap=5):
    sliced = algo_df[(algo_df.index >= start_ts) & (algo_df.index <= end_ts)]
    if len(sliced) < 2:
        return None

    highs  = sliced["High"].values.astype(np.float64)
    lows   = sliced["Low"].values.astype(np.float64)
    closes = sliced["Close"].values.astype(np.float64)
    times  = sliced.index

    blue_vals   = sliced["blue_ray"].values.astype(np.float64)
    purple_vals = sliced["purple_ray"].values.astype(np.float64)

    # Get raw signals
    raw_sigs = sliced[sliced["signal"].isin(["BUY", "SELL"])]
    if raw_sigs.empty:
        return None

    # Apply touch filter — only keep signals where ray has enough touches
    filtered = []
    for ts, row in raw_sigs.iterrows():
        sig = row["signal"]
        price = float(row["buy_price"] if sig == "BUY" else row["sell_price"])
        bar_idx = sliced.index.get_loc(ts)

        if sig == "BUY":
            # Blue ray cross up — check blue ray touch count
            touches = _count_touches(lows, highs, closes, blue_vals, 'up',
                                     touch_proximity, min_bounce, min_bars_gap, bar_idx)
        else:
            # Purple ray cross down — check purple ray touch count
            touches = _count_touches(lows, highs, closes, purple_vals, 'down',
                                     touch_proximity, min_bounce, min_bars_gap, bar_idx)

        if touches >= min_touches:
            filtered.append((ts, sig, price))
        # If not enough touches, skip this signal (stay flat or hold current)

    if not filtered:
        return None

    # Bar-by-bar replay
    tpls = []
    pos, ep, entry_bar = "flat", None, 0
    partial_taken = False
    sig_idx = 0

    for i in range(len(sliced)):
        close = closes[i]

        if PARTIAL_TP > 0 and pos != "flat" and ep is not None and not partial_taken:
            unreal = (close - ep) if pos == "long" else (ep - close)
            if unreal >= PARTIAL_TP:
                tpls.append(unreal)
                partial_taken = True

        if sig_idx < len(filtered) and times[i] == filtered[sig_idx][0]:
            ts, sig, price = filtered[sig_idx]; sig_idx += 1
            if pos == "long" and sig == "SELL":
                tpls.append(price - ep)
                pos, ep, entry_bar = "short", price, i; partial_taken = False
            elif pos == "short" and sig == "BUY":
                tpls.append(ep - price)
                pos, ep, entry_bar = "long", price, i; partial_taken = False
            elif pos == "flat":
                pos = "long" if sig == "BUY" else "short"
                ep = price; entry_bar = i

    if pos != "flat" and ep is not None:
        tpls.append((closes[-1] - ep) if pos == "long" else (ep - closes[-1]))

    return sum(tpls) if tpls else None


# ─────────────────────────────────────────────────────────────────────────────
# Scenarios
# ─────────────────────────────────────────────────────────────────────────────
SCENARIOS = {}

def _build_scenarios():
    global SCENARIOS
    SCENARIOS["baseline"] = None  # no touch filter

    for min_t in [2, 3, 4]:
        for prox in [5, 10, 15, 20]:
            for bounce in [20, 30, 50]:
                for gap in [3, 5, 10]:
                    key = f"t{min_t}_p{prox}_b{bounce}_g{gap}"
                    SCENARIOS[key] = dict(
                        min_touches=min_t,
                        touch_proximity=float(prox),
                        min_bounce=float(bounce),
                        min_bars_gap=gap,
                    )

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
        sliced  = algo_df[(algo_df.index >= start_ts) & (algo_df.index <= end_ts)]

        row = {"date": d}
        for name, kwargs in SCENARIOS.items():
            if kwargs is None:
                # baseline — sum raw P&L
                raw = sliced[sliced["signal"].isin(["BUY","SELL"])]
                tpls = []
                pos, ep = "flat", None
                partial_taken = False
                closes = sliced["Close"].values.astype(np.float64)
                times  = sliced.index
                sig_list = [(ts, r["signal"],
                             float(r["buy_price"] if r["signal"]=="BUY" else r["sell_price"]))
                            for ts, r in raw.iterrows()]
                si = 0
                for i in range(len(sliced)):
                    c = closes[i]
                    if PARTIAL_TP > 0 and pos != "flat" and ep is not None and not partial_taken:
                        if ((c - ep) if pos=="long" else (ep - c)) >= PARTIAL_TP:
                            tpls.append((c-ep) if pos=="long" else (ep-c))
                            partial_taken = True
                    if si < len(sig_list) and times[i] == sig_list[si][0]:
                        ts, sig, price = sig_list[si]; si += 1
                        if pos=="long" and sig=="SELL": tpls.append(price-ep); pos,ep="short",price; partial_taken=False
                        elif pos=="short" and sig=="BUY": tpls.append(ep-price); pos,ep="long",price; partial_taken=False
                        elif pos=="flat": pos="long" if sig=="BUY" else "short"; ep=price
                if pos != "flat" and ep is not None:
                    tpls.append((closes[-1]-ep) if pos=="long" else (ep-closes[-1]))
                row[name] = sum(tpls) if tpls else 0.0
            else:
                result = calc_pl_with_touches(algo_df, start_ts, end_ts, **kwargs)
                row[name] = result if result is not None else 0.0
        return row
    except Exception:
        return None


def main():
    files = sorted(glob.glob(os.path.join(_DATA_ROOT, "CBOT_MINI_YM1_*.csv")))
    print(f"Processing {len(files)} days with {len(SCENARIOS)} scenarios ...")
    print("This will take a few minutes due to touch counting overhead...")

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
    print(f"{'Scenario':<28} {'Total Pts':>10} {'Avg/Day':>9} {'Win%':>6} {'WinDays':>8} {'LoseDays':>9}")
    print("=" * 90)

    # Print baseline + top 20
    baseline = summary.loc["baseline"]
    print(f"{'baseline':<28} {baseline['total_pts']:>10.0f} {baseline['avg_pts']:>9.1f} "
          f"{baseline['win_pct']:>6.1f}% {baseline['win_days']:>8.0f} {baseline['lose_days']:>9.0f}  <-- BASELINE")
    print("-" * 90)

    top20 = summary[summary.index != "baseline"].head(20)
    for name, row in top20.iterrows():
        print(f"{name:<28} {row['total_pts']:>10.0f} {row['avg_pts']:>9.1f} "
              f"{row['win_pct']:>6.1f}% {row['win_days']:>8.0f} {row['lose_days']:>9.0f}")

    df.to_csv("_sweep_touchpoints_results.csv")
    summary.to_csv("_sweep_touchpoints_summary.csv")
    print(f"\nFull results saved to _sweep_touchpoints_summary.csv")


if __name__ == "__main__":
    main()
