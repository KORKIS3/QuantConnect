import os, pandas as pd, pytz, matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig
from Plotter import plot_results

_EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

date = "2026-04-17"
start_t = "09:30"
end_t = "10:30"

df = pd.read_csv(os.path.join(DATA_ROOT, f"CBOT_MINI_YM1_{date}.csv"), index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)

import pytz as _pytz
_est = _pytz.timezone("US/Eastern")
ds = pd.Timestamp(f"{date} {start_t}", tz=_est)
de = pd.Timestamp(f"{date} {end_t}", tz=_est)
df = df[(df.index >= ds) & (df.index <= de)]

config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=10,
                    min_entry_angle=30.0)
algo_df = run_trading_algo_fast(df, date, start_t, end_t, config=config)

signals = algo_df[algo_df["signal"].isin(["BUY", "SELL"])]
print(f"\nDate: {date}  {start_t}-{end_t}")
print(f"Bars: {len(algo_df)}  Signals: {len(signals)}")
for ts, row in signals.iterrows():
    sig = row["signal"]
    price = row["buy_price"] if sig == "BUY" else row["sell_price"]
    liq = " [LIQ]" if row["is_liquidation"] else ""
    print(f"  {ts.strftime('%H:%M')}  {sig:4s} @ {int(price)}   P/L: {row['pl']:+.0f} pts{liq}")
print(f"\nFinal P/L: {algo_df['pl'].iloc[-1]:+.0f} pts")

plot_results(algo_df, date, start_t, end_t)
