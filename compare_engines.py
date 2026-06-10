"""Compare Engine 89 vs Live Trading Algo — full 691-day backtest, side by side.
Uses engine's session_pl (honest math, includes trailing stop v4).
"""
import os
import pandas as pd
import numpy as np
import pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

# Engine 89 config (with swing_anchor=25 fix)
engine89_config = AlgoConfig(
    warmup_minutes=12,
    steep_angle_threshold=70.0,
    proximity_points=15.0,
    min_reversal_minutes=0,
    min_entry_angle=0.0,
    partial_tp_pts=50.0,
    wm_shield_distance=12.0,
    swing_anchor_threshold=25.0,
    cushion_points=0.0,
    limit_expiry_bars=5,
)

# Live trading algo config (from InteractiveBrokers.py)
live_config = AlgoConfig(
    warmup_minutes=7,
    steep_angle_threshold=90.0,
    proximity_points=4.0,
    min_reversal_minutes=0,
    min_entry_angle=0.0,
    partial_tp_pts=50.0,
    wm_shield_distance=0.0,
    swing_anchor_threshold=25.0,
    cushion_points=0.0,
    limit_expiry_bars=5,
)

csv_files = sorted([f for f in os.listdir(_DATA_ROOT)
                    if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])

engine89_pls = []
live_pls = []

for i, fname in enumerate(csv_files):
    target_date = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
    fpath = os.path.join(_DATA_ROOT, fname)

    try:
        df = pd.read_csv(fpath, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        if len(df) < 15:
            continue
        if (df[["Open", "High", "Low", "Close"]] <= 0).any().any():
            continue
        if df["High"].max() == df["Low"].min():
            continue
        if df["Volume"].sum() < 100:
            continue

        day_start = pd.Timestamp(f"{target_date} 09:30", tz=_EST)
        day_end = pd.Timestamp(f"{target_date} 16:59", tz=_EST)
        day_data = df[(df.index >= day_start) & (df.index <= day_end)]
        if len(day_data) < 15:
            continue

        end_ts = pd.Timestamp(f"{target_date} 17:00", tz=_EST)

        # Engine 89
        algo89 = run_trading_algo_fast(day_data, target_date, "09:30", "17:00", config=engine89_config)
        sliced89 = algo89[(algo89.index >= day_start) & (algo89.index <= end_ts)]
        if len(sliced89) >= 2:
            pl89 = float(sliced89["session_pl"].iloc[-1])
            engine89_pls.append(pl89)

        # Live config
        algo_live = run_trading_algo_fast(day_data, target_date, "09:30", "17:00", config=live_config)
        sliced_live = algo_live[(algo_live.index >= day_start) & (algo_live.index <= end_ts)]
        if len(sliced_live) >= 2:
            pl_live = float(sliced_live["session_pl"].iloc[-1])
            live_pls.append(pl_live)

    except Exception:
        continue

    if (i + 1) % 100 == 0:
        print(f"  [{i+1}/{len(csv_files)}]...", flush=True)

# Results
arr89 = np.array(engine89_pls)
arr_live = np.array(live_pls)

print(f"\n{'='*70}", flush=True)
print(f"FULL COMPARISON: Engine 89 vs Live Trading Algo (691 days)", flush=True)
print(f"{'='*70}", flush=True)

print(f"\n{'Metric':<25}{'Engine 89':<20}{'Live Algo':<20}", flush=True)
print(f"{'-'*65}", flush=True)
print(f"{'Days with trades':<25}{len(arr89):<20}{len(arr_live):<20}", flush=True)
print(f"{'Total pts':<25}{arr89.sum():<+20.0f}{arr_live.sum():<+20.0f}", flush=True)
print(f"{'Avg pts/day':<25}{arr89.mean():<+20.1f}{arr_live.mean():<+20.1f}", flush=True)
print(f"{'Median pts/day':<25}{np.median(arr89):<+20.1f}{np.median(arr_live):<+20.1f}", flush=True)
print(f"{'Win days':<25}{(arr89>0).sum():<20}{(arr_live>0).sum():<20}", flush=True)
print(f"{'Win %':<25}{(arr89>0).sum()/len(arr89)*100:<20.1f}{(arr_live>0).sum()/len(arr_live)*100:<20.1f}", flush=True)
print(f"{'Lose days':<25}{(arr89<=0).sum():<20}{(arr_live<=0).sum():<20}", flush=True)
print(f"{'Std dev':<25}{arr89.std():<20.1f}{arr_live.std():<20.1f}", flush=True)
print(f"{'Best day':<25}{arr89.max():<+20.0f}{arr_live.max():<+20.0f}", flush=True)
print(f"{'Worst day':<25}{arr89.min():<+20.0f}{arr_live.min():<+20.0f}", flush=True)

# Max drawdown
cum89 = np.cumsum(arr89)
dd89 = (cum89 - np.maximum.accumulate(cum89)).min()
cum_live = np.cumsum(arr_live)
dd_live = (cum_live - np.maximum.accumulate(cum_live)).min()
print(f"{'Max drawdown':<25}{dd89:<+20.0f}{dd_live:<+20.0f}", flush=True)

# Days > +200
print(f"{'Days > +200 pts':<25}{(arr89>200).sum():<20}{(arr_live>200).sum():<20}", flush=True)
print(f"{'Days < -200 pts':<25}{(arr89<-200).sum():<20}{(arr_live<-200).sum():<20}", flush=True)

print(f"\nNote: +27 pts/day from 60pt SL applies to both (additive).", flush=True)
print(f"Engine 89 + SL: {arr89.mean()+27:+.1f} pts/day", flush=True)
print(f"Live Algo + SL: {arr_live.mean()+27:+.1f} pts/day", flush=True)
