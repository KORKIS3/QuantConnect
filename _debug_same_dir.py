"""Prove or disprove: does reset-entry = hold for same-direction signals?"""
import os, pandas as pd, pytz
from TradingAlgo import AlgoConfig
from TradingAlgoFast import run_trading_algo_fast
import Backtest2Year as bt

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0,
                    max_loss_per_trade=0, line_tolerance=100.0)

dd = "2026-02-25"
df = pd.read_csv(os.path.join(_DATA_ROOT, f"CBOT_MINI_YM1_{dd}.csv"), index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
ds = pd.Timestamp(f"{dd} 09:30", tz=_EST); de = pd.Timestamp(f"{dd} 17:00", tz=_EST)
dd_data = df[(df.index >= ds) & (df.index <= de)]
algo = run_trading_algo_fast(dd_data, dd, "09:30", "17:00", config=config)

# Method 1: proven backtest (reset entry)
tpls = bt._filter_and_calc_pl(algo, ds, de, partial_tp_pts=50)
print(f"Method 1 (reset entry): {sum(tpls):.0f} pts, {len(tpls)} entries in tpls")
print(f"  tpls: {[round(x,1) for x in tpls]}")

# Show the filtered signals
rows = algo[algo["signal"].isin(["BUY","SELL"])]
filtered = []
for ts, row in rows.iterrows():
    sig = row["signal"]; price = float(row["buy_price"] if sig=="BUY" else row["sell_price"])
    if not filtered: filtered.append((ts, sig, price)); continue
    lt, ls, _ = filtered[-1]
    if ls != sig and (ts-lt).total_seconds()/60 >= 10: filtered.append((ts, sig, price))
    elif ls == sig: filtered.append((ts, sig, price))

print(f"\nFiltered signals ({len(filtered)} total):")
for ts, sig, price in filtered:
    print(f"  {ts.strftime('%H:%M')}  {sig} @ {price:.0f}")

# Method 2: ignore same-direction (hold)
filtered_no_same = []
for ts, sig, price in filtered:
    if not filtered_no_same: filtered_no_same.append((ts, sig, price)); continue
    lt, ls, _ = filtered_no_same[-1]
    if ls != sig:
        filtered_no_same.append((ts, sig, price))
    # else: skip same-direction

print(f"\nFiltered (no same-dir) signals ({len(filtered_no_same)} total):")
for ts, sig, price in filtered_no_same:
    print(f"  {ts.strftime('%H:%M')}  {sig} @ {price:.0f}")
