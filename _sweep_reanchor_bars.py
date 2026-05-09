"""Sweep reanchor_swing_threshold to find the optimal swing qualification level.
Tests values: 5, 8, 10, 15, 20, 25, 30 pts
reanchor_min_bars fixed at 30 (proven best from prior sweep).
Baseline (reanchor disabled) included for reference.
Current target to beat: 276.5 pts/day, 79.6% win rate, 119 losing days
"""

import os, time
import pandas as pd, pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

_EST       = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

SWEEP_VALUES = [5, 8, 10, 15, 20, 25, 30]  # reanchor_swing_threshold values to test
INCLUDE_DISABLED = True


def _base_config(swing_threshold, reanchor_enabled=True):
    return AlgoConfig(
        warmup_minutes=12,
        steep_angle_threshold=70.0,
        proximity_points=15.0,
        min_reversal_minutes=0,
        min_entry_angle=30.0,
        partial_tp_pts=50.0,
        spike_profit_pts=100.0,
        spike_profit_bars=5,
        wm_shield_distance=12.0,
        steep_line_reentry=True,
        reanchor_blue_purple=reanchor_enabled,
        reanchor_min_bars=30,
        reanchor_swing_threshold=swing_threshold,
    )


def _run_one(fpath, target_date, config):
    try:
        df = pd.read_csv(fpath, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        if len(df) < 10:
            return None
        day_start = pd.Timestamp(f"{target_date} 09:30", tz=_EST)
        day_end   = pd.Timestamp(f"{target_date} 16:59", tz=_EST)
        day_data  = df[(df.index >= day_start) & (df.index <= day_end)]
        if len(day_data) < 15:
            return None
        algo_df = run_trading_algo_fast(day_data, target_date, "09:30", "17:00", config=config)
        end_ts  = pd.Timestamp(f"{target_date} 17:00", tz=_EST)
        sliced  = algo_df[(algo_df.index >= day_start) & (algo_df.index <= end_ts)]
        if len(sliced) < 2:
            return None
        return float(sliced["session_pl"].iloc[-1])
    except Exception:
        return None


def run_sweep(csv_files, label, swing_threshold, reanchor_enabled=True):
    config = _base_config(swing_threshold, reanchor_enabled)
    daily_pls = []
    for f in csv_files:
        target_date = f.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
        fpath = os.path.join(_DATA_ROOT, f)
        r = _run_one(fpath, target_date, config)
        if r is not None:
            daily_pls.append(r)

    days    = len(daily_pls)
    total   = sum(daily_pls)
    avg     = total / days if days > 0 else 0.0
    winners = sum(1 for p in daily_pls if p > 0)
    losers  = sum(1 for p in daily_pls if p <= 0)
    win_pct = 100.0 * winners / days if days > 0 else 0.0
    return {"label": label, "days": days, "total": total, "avg": avg,
            "win_pct": win_pct, "winners": winners, "losers": losers}


if __name__ == "__main__":
    csv_files = sorted([f for f in os.listdir(_DATA_ROOT)
                        if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])
    print(f"Sweeping reanchor_swing_threshold across {len(csv_files)} days (full day 9:30-17:00)")
    print(f"Baseline to beat: 276.5 pts/day, 79.6% win%, 119 losing days\n")

    rows = []

    if INCLUDE_DISABLED:
        print("  Running: reanchor=OFF (baseline) ...")
        t0 = time.time()
        r = run_sweep(csv_files, "OFF (baseline)", 5.0, reanchor_enabled=False)
        print(f"    done in {time.time()-t0:.1f}s  →  {r['avg']:+.1f} pts/day, {r['win_pct']:.1f}% win, {r['losers']} losing days")
        rows.append(r)

    for val in SWEEP_VALUES:
        label = f"swing_thresh={val}pts"
        print(f"  Running: {label} ...")
        t0 = time.time()
        r = run_sweep(csv_files, label, float(val), reanchor_enabled=True)
        print(f"    done in {time.time()-t0:.1f}s  →  {r['avg']:+.1f} pts/day, {r['win_pct']:.1f}% win, {r['losers']} losing days")
        rows.append(r)

    print(f"\n{'Label':<24} {'Days':>5} {'Avg/Day':>9} {'Win%':>7} {'Winners':>8} {'Losers':>7} {'Total Pts':>10}")
    print("-" * 76)
    for r in rows:
        marker = " ◄ BEST" if r == max(rows, key=lambda x: x["avg"]) else ""
        print(f"{r['label']:<24} {r['days']:>5} {r['avg']:>+9.1f} {r['win_pct']:>6.1f}% "
              f"{r['winners']:>8} {r['losers']:>7} {r['total']:>+10.0f}{marker}")
    print()
    best = max(rows, key=lambda x: x["avg"])
    print(f"Best: {best['label']}  →  {best['avg']:+.1f} pts/day, {best['win_pct']:.1f}% win, {best['losers']} losing days")

