"""
Sweep trailing stop angles — testing shallower angles (5-25 degrees)
since 50/60/70 were proven to be too steep (overtake price).
Full 667 days, 9:30-17:00.
"""
import os, glob
import pandas as pd
import numpy as np
import pytz
from multiprocessing import Pool, cpu_count
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig
from _sweep_trailing import _apply_trailing

_EST       = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.expanduser("~/Desktop/2YearsData/full_day")

BASE_CONFIG = AlgoConfig(
    warmup_minutes=12, steep_angle_threshold=70.0, proximity_points=15.0,
    min_reversal_minutes=0, min_entry_angle=30.0, partial_tp_pts=50.0,
    spike_profit_pts=99999.0,
)

SCENARIOS = {
    "no_trailing": dict(threshold=99999),
    "current_v4":  dict(threshold=50, base_angle=50, mid_angle=60, high_angle=70,
                        mid_profit=100, high_profit=150, lock_anchor=True, progressive=False),
}

# Sweep shallower angles — base 5-25, high base+5 to base+15
for base in [5, 8, 10, 12, 15, 18, 20, 25]:
    for spread in [5, 10, 15]:
        high = base + spread
        mid  = (base + high) // 2
        key  = f"b{base}_h{high}"
        SCENARIOS[key] = dict(threshold=50, base_angle=float(base), mid_angle=float(mid),
                              high_angle=float(high), mid_profit=100, high_profit=150,
                              lock_anchor=True, progressive=False)

def _process_file(fpath):
    d = os.path.basename(fpath).replace("CBOT_MINI_YM1_", "").replace(".csv", "")
    try:
        df = pd.read_csv(fpath, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        start_ts = pd.Timestamp(f"{d} 09:30", tz=_EST)
        end_ts   = pd.Timestamp(f"{d} 17:00", tz=_EST)
        day_data = df[(df.index >= start_ts) & (df.index <= end_ts)]
        if len(day_data) < 15: return None
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
    print(f"Processing {len(files)} days, {len(SCENARIOS)} scenarios ...")
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
    print(f"\n{'='*80}")
    print(f"{'Scenario':<20} {'Total Pts':>10} {'Avg/Day':>9} {'Win%':>6} {'WinDays':>8} {'LoseDays':>9}")
    print(f"{'='*80}")
    for name, row in summary.iterrows():
        marker = " <-- NO TRAIL" if name == "no_trailing" else (" <-- CURRENT V4 (broken)" if name == "current_v4" else "")
        print(f"{name:<20} {row['total_pts']:>10.0f} {row['avg_pts']:>9.1f} "
              f"{row['win_pct']:>6.1f}% {row['win_days']:>8.0f} {row['lose_days']:>9.0f}{marker}")

if __name__ == "__main__":
    main()
