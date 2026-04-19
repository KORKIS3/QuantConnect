"""Spot check: compare old regression vs new tolerance=500 on a few key days."""
import os
import pandas as pd, pytz
from TradingAlgo import AlgoConfig
from TradingAlgoFast import run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0,
                    max_loss_per_trade=0, line_tolerance=500.0)

test_dates = ["2026-02-04", "2026-02-10", "2026-02-11", "2026-02-23", "2025-04-07"]

print(f"{'Date':<12} {'Signals':<40} {'Raw P/L':>10}")
print("-" * 65)
for dd in test_dates:
    fname = os.path.join(_DATA_ROOT, f"CBOT_MINI_YM1_{dd}.csv")
    if not os.path.exists(fname): print(f"{dd}: no file"); continue
    df = pd.read_csv(fname, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    ds = pd.Timestamp(f"{dd} 09:30", tz=_EST)
    de = pd.Timestamp(f"{dd} 17:00", tz=_EST)
    dd_data = df[(df.index >= ds) & (df.index <= de)]
    if len(dd_data) < 15: print(f"{dd}: not enough data"); continue
    algo = run_trading_algo_fast(dd_data, dd, "09:30", "17:00", config=config)
    sigs = algo[algo["signal"].isin(["BUY","SELL"])]
    sig_str = " ".join([f"{ts.strftime('%H:%M')}:{row['signal']}" for ts, row in sigs.iterrows()])
    raw_pl = float(algo["pl"].iloc[-1])
    print(f"{dd:<12} {sig_str:<40} {raw_pl:>+10.0f} pts")
