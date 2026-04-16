"""Find the top 5 worst and best DAYS by net daily P/L."""

import os
import pandas as pd
import pytz
from TradingAlgo import run_trading_algo, AlgoConfig
from Backtest2Year import calc_pl

_EST       = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1000")

config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=10)

csv_files = sorted([
    f for f in os.listdir(_DATA_ROOT)
    if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")
])

daily_results = []

for fname in csv_files:
    target_date = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
    if target_date.startswith("2025-04"):
        continue
    fpath = os.path.join(_DATA_ROOT, fname)
    try:
        df = pd.read_csv(fpath, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        if len(df) < 10:
            continue
        algo_df = run_trading_algo(df, target_date, "09:30", "10:30", config=config)
    except Exception:
        continue

    trade_pls = calc_pl(algo_df, float(algo_df["Close"].iloc[-1]), min_minutes=10)
    if not trade_pls:
        continue

    day_pl = sum(trade_pls)
    n_trades = len(trade_pls)

    # Get signal details
    signals = algo_df[algo_df["signal"].isin(["BUY","SELL"])]
    sig_summary = []
    for ts, row in signals.iterrows():
        sig = row["signal"]
        price = float(row["buy_price"] if sig == "BUY" else row["sell_price"])
        sig_summary.append(f"{ts.strftime('%H:%M')} {sig} @{int(price)}")

    daily_results.append({
        "date": target_date,
        "pl": round(day_pl, 0),
        "trades": n_trades,
        "signals": " | ".join(sig_summary),
    })

daily_df = pd.DataFrame(daily_results).sort_values("pl")

print("TOP 10 WORST DAYS (net daily P/L):")
for _, row in daily_df.head(10).iterrows():
    print(f"  {row['date']}  P/L: {row['pl']:+.0f} pts  trades: {row['trades']}  {row['signals']}")

print(f"\nTOP 10 BEST DAYS:")
for _, row in daily_df.tail(10).iterrows():
    print(f"  {row['date']}  P/L: {row['pl']:+.0f} pts  trades: {row['trades']}  {row['signals']}")
