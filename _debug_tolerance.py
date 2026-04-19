"""Debug: show exactly what signals fire at different tolerances on key days."""
import os
import pandas as pd, pytz
from TradingAlgo import AlgoConfig
from TradingAlgoFast import run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

test_dates = ["2026-02-23", "2026-02-04", "2026-02-10"]
tolerances = [1, 50, 100]

for dd in test_dates:
    fname = os.path.join(_DATA_ROOT, f"CBOT_MINI_YM1_{dd}.csv")
    if not os.path.exists(fname): continue
    df = pd.read_csv(fname, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    ds = pd.Timestamp(f"{dd} 09:30", tz=_EST)
    de = pd.Timestamp(f"{dd} 10:30", tz=_EST)  # just first hour for clarity
    dd_data = df[(df.index >= ds) & (df.index <= de)]
    if len(dd_data) < 15: continue

    print(f"\n{'='*70}")
    print(f"  {dd}  (9:30-10:30 only)")
    print(f"{'='*70}")

    for tol in tolerances:
        config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                            proximity_points=15.0, min_reversal_minutes=0,
                            max_loss_per_trade=0, line_tolerance=float(tol))
        algo = run_trading_algo_fast(dd_data, dd, "09:30", "10:30", config=config)
        sigs = algo[algo["signal"].isin(["BUY","SELL"])]

        print(f"\n  tol={tol}:")
        for ts, row in sigs.iterrows():
            sig = row["signal"]
            price = float(row["buy_price"] if sig == "BUY" else row["sell_price"])
            p = float(row["purple_ray"])
            b = float(row["blue_ray"])
            c = float(row["Close"])
            print(f"    {ts.strftime('%H:%M')}  {sig:4s} @ {price:.0f}  close={c:.0f}  purple={p:.0f}  blue={b:.0f}")
        if sigs.empty:
            print(f"    (no signals)")
