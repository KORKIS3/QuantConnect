"""Verify TradingAlgo and TradingAlgoFast produce matching signals."""
import os
import pandas as pd, pytz
from TradingAlgo import run_trading_algo, AlgoConfig
from TradingAlgoFast import run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0, max_loss_per_trade=999)

test_dates = ["2026-02-03", "2026-02-05", "2026-02-09", "2026-02-23", "2025-04-07"]
for dd in test_dates:
    fname = os.path.join(_DATA_ROOT, f"CBOT_MINI_YM1_{dd}.csv")
    if not os.path.exists(fname):
        print(f"{dd}: file not found"); continue
    df = pd.read_csv(fname, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    ds = pd.Timestamp(f"{dd} 09:30", tz=_EST)
    de = pd.Timestamp(f"{dd} 10:30", tz=_EST)
    dd_data = df[(df.index >= ds) & (df.index <= de)]
    if len(dd_data) < 15: print(f"{dd}: not enough data"); continue

    algo = run_trading_algo(dd_data, dd, "09:30", "10:30", config=config)
    fast = run_trading_algo_fast(dd_data, dd, "09:30", "10:30", config=config)

    # Compare signals
    algo_sigs = [(ts.strftime("%H:%M"), row["signal"]) for ts, row in algo.iterrows() if row["signal"] in ("BUY", "SELL")]
    fast_sigs = [(ts.strftime("%H:%M"), row["signal"]) for ts, row in fast.iterrows() if row["signal"] in ("BUY", "SELL")]

    if algo_sigs == fast_sigs:
        print(f"{dd}: MATCH ({len(algo_sigs)} signals)")
    else:
        print(f"{dd}: MISMATCH")
        print(f"  algo: {algo_sigs}")
        print(f"  fast: {fast_sigs}")

    # Compare purple values at a few bars
    mismatches = 0
    for i in range(min(len(algo), len(fast))):
        ap = algo["purple_ray"].iloc[i]
        fp = fast["purple_ray"].iloc[i]
        if abs(ap - fp) > 2:
            if mismatches < 3:
                t = algo.index[i].strftime("%H:%M")
                print(f"  purple mismatch at {t}: algo={ap:.0f} fast={fp:.0f}")
            mismatches += 1
    if mismatches > 3:
        print(f"  ... {mismatches} total purple mismatches")
    elif mismatches == 0:
        print(f"  purple values match")
