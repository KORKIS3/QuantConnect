"""Find the top 5 biggest losing trades and identify the dates."""

import os
import pandas as pd
import pytz
from TradingAlgoFast import run_trading_algo_fast as run_trading_algo, AlgoConfig
from Backtest2Year import calc_pl

_EST       = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1000")

config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=10)

csv_files = sorted([
    f for f in os.listdir(_DATA_ROOT)
    if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")
])

all_trades = []

for fname in csv_files:
    target_date = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
    fpath = os.path.join(_DATA_ROOT, fname)
    try:
        df = pd.read_csv(fpath, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        if len(df) < 10:
            continue
        algo_df = run_trading_algo(df, target_date, "09:30", "10:30", config=config)
    except Exception:
        continue

    signals = algo_df[algo_df["signal"].isin(["BUY","SELL"])].copy()
    if signals.empty:
        continue

    # Build signal list — no additional filtering needed, algo already applied min_reversal
    filtered = []
    for ts, row in signals.iterrows():
        sig   = row["signal"]
        price = float(row["buy_price"] if sig == "BUY" else row["sell_price"])
        filtered.append((ts, sig, price))

    last_close = float(algo_df["Close"].iloc[-1])
    position = "flat"
    entry_price = None
    entry_time  = None
    entry_sig   = None

    for i, (ts, sig, price) in enumerate(filtered):
        if sig == "BUY":
            if position == "short" and entry_price is not None:
                pl = entry_price - price
                all_trades.append({
                    "date": target_date,
                    "direction": "SHORT",
                    "entry_time": entry_time.strftime("%H:%M"),
                    "exit_time": ts.strftime("%H:%M"),
                    "entry_price": int(entry_price),
                    "exit_price": int(price),
                    "pl": round(pl, 0),
                })
            position, entry_price, entry_time = "long", price, ts
        elif sig == "SELL":
            if position == "long" and entry_price is not None:
                pl = price - entry_price
                all_trades.append({
                    "date": target_date,
                    "direction": "LONG",
                    "entry_time": entry_time.strftime("%H:%M"),
                    "exit_time": ts.strftime("%H:%M"),
                    "entry_price": int(entry_price),
                    "exit_price": int(price),
                    "pl": round(pl, 0),
                })
            position, entry_price, entry_time = "short", price, ts

    # Open position at session end
    if position != "flat" and entry_price is not None:
        pl = (last_close - entry_price) if position == "long" else (entry_price - last_close)
        all_trades.append({
            "date": target_date,
            "direction": position.upper(),
            "entry_time": entry_time.strftime("%H:%M"),
            "exit_time": "10:30",
            "entry_price": int(entry_price),
            "exit_price": int(last_close),
            "pl": round(pl, 0),
        })

trades_df = pd.DataFrame(all_trades).sort_values("pl")
print("TOP 10 BIGGEST LOSERS:")
print(trades_df.head(10).to_string(index=False))
print()
print("Dates to review:")
for _, row in trades_df.head(5).iterrows():
    print(f"  {row['date']}  {row['direction']}  {row['entry_time']}-{row['exit_time']}  "
          f"@ {row['entry_price']}->{row['exit_price']}  P/L: {row['pl']:+.0f}")
