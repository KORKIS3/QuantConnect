"""AnalyseBigLosers.py

Identifies all trades losing more than 100 points using the 7-minute
time filter, prints them sorted by loss size, and saves to CSV.
"""

import os
import pandas as pd
import pytz
from TradingAlgoFast import run_trading_algo_fast as run_trading_algo, AlgoConfig
from Backtest2Year import calc_pl

_EST       = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1000")
MIN_MINUTES = 7
LOSS_THRESHOLD = -100   # show trades worse than this


def get_big_losers() -> pd.DataFrame:
    csv_files = sorted([
        f for f in os.listdir(_DATA_ROOT)
        if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")
    ])
    config = AlgoConfig(warmup_minutes=7, steep_angle_threshold=65.0, proximity_points=15.0)
    records = []

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

        signals = algo_df[algo_df["signal"].isin(["BUY", "SELL"])].copy()
        if signals.empty:
            continue

        # Build filtered signal list with 7-min time filter.
        filtered = []
        for ts, row in signals.iterrows():
            sig   = row["signal"]
            price = float(row["buy_price"] if sig == "BUY" else row["sell_price"])
            if not filtered:
                filtered.append((ts, sig, price))
                continue
            last_ts, last_sig, last_price = filtered[-1]
            if last_sig != sig:
                mins_held = (ts - last_ts).total_seconds() / 60
                if mins_held >= MIN_MINUTES:
                    filtered.append((ts, sig, price))
            else:
                filtered.append((ts, sig, price))

        if not filtered:
            continue

        last_close = float(algo_df["Close"].iloc[-1])

        # Calculate per-trade P/L with entry/exit details.
        position    = "flat"
        entry_price = None
        entry_time  = None
        entry_sig   = None

        for i, (ts, sig, price) in enumerate(filtered):
            if sig == "BUY":
                if position == "short" and entry_price is not None:
                    pl = entry_price - price
                    if pl <= LOSS_THRESHOLD:
                        records.append({
                            "date":        target_date,
                            "entry_time":  entry_time.strftime("%H:%M"),
                            "exit_time":   ts.strftime("%H:%M"),
                            "direction":   "SHORT",
                            "entry_price": int(entry_price),
                            "exit_price":  int(price),
                            "pl_pts":      round(pl, 0),
                            "mins_held":   round((ts - entry_time).total_seconds() / 60, 1),
                        })
                position    = "long"
                entry_price = price
                entry_time  = ts
                entry_sig   = sig

            elif sig == "SELL":
                if position == "long" and entry_price is not None:
                    pl = price - entry_price
                    if pl <= LOSS_THRESHOLD:
                        records.append({
                            "date":        target_date,
                            "entry_time":  entry_time.strftime("%H:%M"),
                            "exit_time":   ts.strftime("%H:%M"),
                            "direction":   "LONG",
                            "entry_price": int(entry_price),
                            "exit_price":  int(price),
                            "pl_pts":      round(pl, 0),
                            "mins_held":   round((ts - entry_time).total_seconds() / 60, 1),
                        })
                position    = "short"
                entry_price = price
                entry_time  = ts
                entry_sig   = sig

        # Check open position at session end.
        if position != "flat" and entry_price is not None:
            pl = (last_close - entry_price) if position == "long" else (entry_price - last_close)
            if pl <= LOSS_THRESHOLD:
                records.append({
                    "date":        target_date,
                    "entry_time":  entry_time.strftime("%H:%M"),
                    "exit_time":   "10:30",
                    "direction":   position.upper(),
                    "entry_price": int(entry_price),
                    "exit_price":  int(last_close),
                    "pl_pts":      round(pl, 0),
                    "mins_held":   round((algo_df.index[-1] - entry_time).total_seconds() / 60, 1),
                })

    return pd.DataFrame(records).sort_values("pl_pts")


if __name__ == "__main__":
    print(f"Finding all trades with loss > {abs(LOSS_THRESHOLD)} pts (7-min filter)...\n")
    df = get_big_losers()

    if df.empty:
        print("No big losers found.")
    else:
        print(f"Found {len(df)} trades losing more than {abs(LOSS_THRESHOLD)} points:\n")
        pd.set_option("display.width", 120)
        pd.set_option("display.max_rows", 200)
        print(df.to_string(index=False))

        print(f"\nTotal loss from these trades: {df['pl_pts'].sum():.0f} pts  "
              f"${df['pl_pts'].sum()*100*5:,.0f}")
        print(f"Average loss: {df['pl_pts'].mean():.0f} pts")
        print(f"Worst loss:   {df['pl_pts'].min():.0f} pts  ({df.iloc[0]['date']} {df.iloc[0]['direction']})")

        print(f"\nBy direction:")
        print(df.groupby("direction")["pl_pts"].agg(["count","sum","mean"]).round(1))

        print(f"\nBy entry time (how many big losers start at each time):")
        print(df["entry_time"].value_counts().head(10))

        # Save to CSV.
        out = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "big_losers_7min.csv")
        df.to_csv(out, index=False)
        print(f"\nSaved to: {out}")
