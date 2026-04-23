import os, glob
import pandas as pd
import numpy as np
import pytz
import matplotlib.dates as mdates
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
    "v4_trailing": dict(threshold=50, base_angle=50, mid_angle=60, high_angle=70,
                        mid_profit=100, high_profit=150, lock_anchor=True, progressive=False),
}

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
    print(f"Processing {len(files)} days ...")
    with Pool(max(1, cpu_count() - 1)) as pool:
        results = pool.map(_process_file, files)
    results = [r for r in results if r is not None]
    df = pd.DataFrame(results).set_index("date")

    print("\n" + "=" * 70)
    print(f"{'Scenario':<20} {'Total Pts':>10} {'Avg/Day':>9} {'Win% Day':>9} {'WinDays':>8} {'LoseDays':>9}")
    print("=" * 70)
    for name in SCENARIOS:
        col = df[name]
        wins = (col > 0).sum(); loses = (col < 0).sum()
        print(f"{name:<20} {col.sum():>10.0f} {col.mean():>9.1f} "
              f"{wins/(wins+loses)*100:>9.1f}% {wins:>8} {loses:>9}")

    diff = df["v4_trailing"] - df["no_trailing"]
    print(f"\nv4 vs no trailing:")
    print(f"  Avg pts/day difference: {diff.mean():+.1f}")
    print(f"  Days improved:          {(diff > 0).sum()}")
    print(f"  Days hurt:              {(diff < 0).sum()}")
    print(f"  Days same:              {(diff == 0).sum()}")

if __name__ == "__main__":
    main()
