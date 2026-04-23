"""
_sweep_filters.py
-----------------
Tests two filter ideas across all 664 days (9:30-10:30 window):

1. Opening range filter — skip first signal if price moved > N pts from 9:30 open
2. 10-min reversal rule by time window — turn on/off in 30-min buckets

Run:  python _sweep_filters.py
"""

import os, glob
import pandas as pd
import numpy as np
import pytz
from multiprocessing import Pool, cpu_count
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig
from Backtest2Year import _find_wm_clusters

_EST      = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.expanduser("~/Desktop/2YearsData/full_day")
_END_TIME  = "17:00"

# ── baseline config (proven settings, min_reversal_minutes handled post-hoc) ──
BASE_CONFIG = AlgoConfig(
    warmup_minutes=12,
    steep_angle_threshold=70.0,
    proximity_points=15.0,
    min_reversal_minutes=0,   # we apply reversal filter post-hoc so we can vary it
    min_entry_angle=30.0,
    partial_tp_pts=50.0,
)

# ─────────────────────────────────────────────────────────────────────────────
# Post-hoc P&L calculator with configurable filters
# ─────────────────────────────────────────────────────────────────────────────
def calc_pl(algo_df, start_ts, end_ts,
            open_range_pts=0,        # 0 = disabled; skip first signal if |open - entry| > this
            reversal_windows=None,   # list of (start_min, end_min, min_hold_min)
                                     #   e.g. [(0,30,10),(30,60,0)] means hold 10min in first 30, none after
            ):
    """
    open_range_pts : float  — if > 0, suppress the FIRST signal of the day when
                              abs(open_price - signal_price) > open_range_pts
    reversal_windows : list of (start_offset_min, end_offset_min, min_hold_min)
                       offset is minutes from session start (9:30).
                       If None, uses flat 10-min hold for all.
    """
    sliced = algo_df[(algo_df.index >= start_ts) & (algo_df.index <= end_ts)]
    if len(sliced) < 2:
        return None

    rows = sliced[sliced["signal"].isin(["BUY", "SELL"])]
    if rows.empty:
        return None

    open_price = float(sliced["Close"].iloc[0])

    # ── opening range filter ──────────────────────────────────────────────────
    signal_list = [(ts, row["signal"],
                    float(row["buy_price"] if row["signal"] == "BUY" else row["sell_price"]))
                   for ts, row in rows.iterrows()]

    if open_range_pts > 0 and signal_list:
        first_ts, first_sig, first_price = signal_list[0]
        if abs(first_price - open_price) > open_range_pts:
            signal_list = signal_list[1:]   # drop first signal

    if not signal_list:
        return None

    # ── reversal hold filter ──────────────────────────────────────────────────
    def _min_hold(ts):
        """Return the minimum hold minutes required at this timestamp."""
        if reversal_windows is None:
            return 10
        offset = (ts - start_ts).total_seconds() / 60
        for s, e, h in reversal_windows:
            if s <= offset < e:
                return h
        return 10   # default

    filtered = []
    for ts, sig, price in signal_list:
        if not filtered:
            filtered.append((ts, sig, price))
            continue
        last_ts, last_sig, _ = filtered[-1]
        if last_sig != sig:
            hold = _min_hold(ts)
            if (ts - last_ts).total_seconds() / 60 >= hold:
                filtered.append((ts, sig, price))
        else:
            filtered.append((ts, sig, price))

    if not filtered:
        return None

    # ── bar-by-bar replay (partial TP + spike exit) ───────────────────────────
    closes = sliced["Close"].values.astype(float)
    times  = sliced.index
    sig_idx = 0
    tpls = []
    pos, ep, entry_bar = "flat", None, 0
    partial_taken = False
    PARTIAL_TP = 50.0
    SPIKE_PTS  = 100.0
    SPIKE_BARS = 5

    for i in range(len(sliced)):
        if PARTIAL_TP > 0 and pos != "flat" and ep is not None and not partial_taken:
            unreal = (closes[i] - ep) if pos == "long" else (ep - closes[i])
            if unreal >= PARTIAL_TP:
                tpls.append(unreal)
                partial_taken = True

        if sig_idx < len(filtered) and times[i] == filtered[sig_idx][0]:
            ts, sig, price = filtered[sig_idx]; sig_idx += 1
            if pos == "long" and sig == "SELL":
                tpls.append(price - ep); pos, ep, entry_bar = "short", price, i; partial_taken = False
            elif pos == "short" and sig == "BUY":
                tpls.append(ep - price); pos, ep, entry_bar = "long",  price, i; partial_taken = False
            elif pos == "flat":
                pos = "long" if sig == "BUY" else "short"; ep = price; entry_bar = i
            continue

        if pos != "flat" and ep is not None and 0 < (i - entry_bar) <= SPIKE_BARS:
            move = (closes[i] - ep) if pos == "long" else (ep - closes[i])
            if move >= SPIKE_PTS:
                tpls.append(move); pos, ep, entry_bar = "flat", None, 0; partial_taken = False

    if pos != "flat" and ep is not None:
        tpls.append((closes[-1] - ep) if pos == "long" else (ep - closes[-1]))

    return sum(tpls) if tpls else None


# ─────────────────────────────────────────────────────────────────────────────
# Worker — runs one day, returns dict of scenario -> pts
# ─────────────────────────────────────────────────────────────────────────────
SCENARIOS = {}

def _build_scenarios():
    global SCENARIOS
    # 1. Baseline (10-min hold all session)
    SCENARIOS["baseline"] = dict(open_range_pts=0, reversal_windows=None)

    # 2. Opening range filter sweep (no change to reversal rule)
    for pts in [100, 150, 200, 250, 300]:
        SCENARIOS[f"open_range_{pts}"] = dict(open_range_pts=pts, reversal_windows=None)

    # 3. Reversal window sweep — vary hold time in 60-min buckets across full day
    # A=9:30-10:30, B=10:30-12:00, C=12:00-14:00, D=14:00-17:00
    for hold_a in [0, 5, 10]:
        for hold_b in [0, 5, 10]:
            key = f"rev_A{hold_a}_B{hold_b}"
            SCENARIOS[key] = dict(
                open_range_pts=0,
                reversal_windows=[(0, 60, hold_a), (60, 450, hold_b)]
            )

    # 4. Best combos: opening range + reversal windows
    for pts in [150, 200]:
        for hold_a in [0, 10]:
            for hold_b in [0, 10]:
                key = f"combo_or{pts}_A{hold_a}_B{hold_b}"
                SCENARIOS[key] = dict(
                    open_range_pts=pts,
                    reversal_windows=[(0, 60, hold_a), (60, 450, hold_b)]
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
        algo_df = run_trading_algo_fast(day_data, d, "09:30", "10:30", config=BASE_CONFIG)
        row = {"date": d}
        for name, kwargs in SCENARIOS.items():
            result = calc_pl(algo_df, start_ts, end_ts, **kwargs)
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

    # ── Summary ───────────────────────────────────────────────────────────────
    summary = pd.DataFrame({
        "total_pts":  df.sum(),
        "avg_pts":    df.mean(),
        "win_days":   (df > 0).sum(),
        "lose_days":  (df < 0).sum(),
        "flat_days":  (df == 0).sum(),
    })
    summary["win_pct"] = (summary["win_days"] / (summary["win_days"] + summary["lose_days"]) * 100).round(1)
    summary = summary.sort_values("total_pts", ascending=False)

    print("\n" + "=" * 80)
    print(f"{'Scenario':<30} {'Total Pts':>10} {'Avg/Day':>9} {'Win%':>6} {'WinDays':>8} {'LoseDays':>9}")
    print("=" * 80)
    for name, row in summary.iterrows():
        marker = " <-- BASELINE" if name == "baseline" else ""
        print(f"{name:<30} {row['total_pts']:>10.0f} {row['avg_pts']:>9.1f} {row['win_pct']:>6.1f}% "
              f"{row['win_days']:>8.0f} {row['lose_days']:>9.0f}{marker}")

    # Save full results
    df.to_csv("_sweep_filters_results.csv")
    summary.to_csv("_sweep_filters_summary.csv")
    print(f"\nFull results saved to _sweep_filters_results.csv")
    print(f"Summary saved to _sweep_filters_summary.csv")


if __name__ == "__main__":
    main()
