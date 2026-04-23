import os, glob
import pandas as pd
import pytz
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig
from Backtest2Year import _filter_and_calc_pl

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.expanduser("~/Desktop/2YearsData/full_day")

config = AlgoConfig(
    warmup_minutes=12,
    steep_angle_threshold=70.0,
    proximity_points=15.0,
    min_reversal_minutes=10,
    min_entry_angle=30.0,
    partial_tp_pts=50.0,
)

files = sorted(glob.glob(os.path.join(_DATA_ROOT, "CBOT_MINI_YM1_*.csv")))
daily = {}

for fpath in files:
    d = os.path.basename(fpath).replace("CBOT_MINI_YM1_", "").replace(".csv", "")
    try:
        df = pd.read_csv(fpath, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        start_ts = pd.Timestamp(f"{d} 09:30", tz=_EST)
        end_ts   = pd.Timestamp(f"{d} 17:00", tz=_EST)
        day_data = df[(df.index >= start_ts) & (df.index <= end_ts)]
        if len(day_data) < 15:
            continue
        algo_df = run_trading_algo_fast(day_data, d, "09:30", "17:00", config=config)
        tpls = _filter_and_calc_pl(algo_df, start_ts, end_ts, partial_tp_pts=50)
        daily[d] = sum(tpls) if tpls else 0.0
    except Exception as e:
        print(f"  {d}: {e}")

# Group by ISO week
s = pd.Series(daily)
s.index = pd.to_datetime(s.index)
weekly = s.groupby(s.index.to_period("W")).sum()
weekly_sorted = weekly.sort_values()

print("\n--- 10 Worst Weeks ---")
for week, pts in weekly_sorted.head(10).items():
    print(f"  {week}   {pts:+.0f} pts   ${pts*5:+.0f}")

print("\n--- 10 Best Weeks ---")
for week, pts in weekly_sorted.tail(10).iloc[::-1].items():
    print(f"  {week}   {pts:+.0f} pts   ${pts*5:+.0f}")

print(f"\nOverall: {s.sum():+.0f} pts  avg/day: {s.mean():+.1f} pts")
