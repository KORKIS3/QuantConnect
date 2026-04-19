"""Debug 04/07/25 9:42-9:54 in detail."""
import os
import pandas as pd, pytz, numpy as np
from TradingAlgo import AlgoConfig
from TradingAlgoFast import run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0,
                    max_loss_per_trade=0, line_tolerance=500.0)

df = pd.read_csv(os.path.join(_DATA_ROOT, "CBOT_MINI_YM1_2025-04-07.csv"), index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
ds = pd.Timestamp("2025-04-07 09:30", tz=_EST)
de = pd.Timestamp("2025-04-07 17:00", tz=_EST)
algo = run_trading_algo_fast(df[(df.index >= ds) & (df.index <= de)], "2025-04-07", "09:30", "17:00", config=config)

# Raw signals before 10-min filter
raw_sigs = algo[algo["signal"].isin(["BUY","SELL"])]
print("RAW signals (before 10-min filter):")
for ts, row in raw_sigs.iterrows():
    t = ts.strftime("%H:%M")
    if t > "10:00": break
    sig = row["signal"]; price = float(row["buy_price"] if sig=="BUY" else row["sell_price"])
    print(f"  {t}  {sig} @ {price:.0f}")

# Apply 10-min filter
filtered = []
for ts, row in raw_sigs.iterrows():
    sig = row["signal"]; price = float(row["buy_price"] if sig=="BUY" else row["sell_price"])
    if not filtered: filtered.append((ts, sig, price)); continue
    lt, ls, _ = filtered[-1]
    if ls != sig and (ts-lt).total_seconds()/60 >= 10: filtered.append((ts, sig, price))
    elif ls == sig: filtered.append((ts, sig, price))

print("\nFILTERED signals (after 10-min filter):")
for ts, sig, price in filtered:
    t = ts.strftime("%H:%M")
    if t > "10:00": break
    print(f"  {t}  {sig} @ {price:.0f}")

# Show bar-by-bar 9:40-9:55
print("\nBar detail 9:40-9:55:")
print("Time   Close   Purple  Blue    Signal(raw)")
for ts, row in algo.iterrows():
    t = ts.strftime("%H:%M")
    if t < "09:40" or t > "09:55": continue
    c = row["Close"]; p = row["purple_ray"]; b = row["blue_ray"]
    sig = str(row["signal"]) if row["signal"] != "" else ""
    print(f"{t}   {c:.0f}   {p:.0f}   {b:.0f}   {sig}")
