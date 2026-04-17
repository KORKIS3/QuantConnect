"""Reproduce proven results: min_reversal=0 in algo, 10-min post-hoc filter in backtest."""
import os
import pandas as pd, pytz, numpy as np
from TradingAlgo import AlgoConfig
from TradingAlgoFast import run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1130")
_CONTRACTS = 2
_MULTIPLIER = 5

# KEY: min_reversal_minutes=0 — algo fires all signals, backtest filters
config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0, max_loss_per_trade=0)

csv_files = sorted([f for f in os.listdir(_DATA_ROOT) if f.endswith(".csv")])
print(f"Running on {len(csv_files)} days (min_rev=0, post-hoc 10-min filter)...\n", flush=True)

total_pl = 0.0; total_trades = 0; winners = 0; losers = 0; daily_pls = []; done = 0

for fname in csv_files:
    dd = fname[15:25]
    if dd.startswith("2025-04"): done += 1; continue
    df = pd.read_csv(os.path.join(_DATA_ROOT, fname), index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    if len(df) < 10: done += 1; continue

    try:
        algo = run_trading_algo_fast(df, dd, "09:30", "11:30", config=config)
    except:
        done += 1; continue

    # Extract signals
    rows = algo[algo["signal"].isin(["BUY","SELL"])]
    if rows.empty: done += 1; continue

    # Post-hoc 10-min reversal filter (same as original Backtest2Year.py)
    filtered = []
    for ts, row in rows.iterrows():
        sig = row["signal"]
        price = float(row["buy_price"] if sig == "BUY" else row["sell_price"])
        if not filtered:
            filtered.append((ts, sig, price)); continue
        last_ts, last_sig, _ = filtered[-1]
        if last_sig != sig:
            if (ts - last_ts).total_seconds() / 60 >= 10:
                filtered.append((ts, sig, price))
        else:
            filtered.append((ts, sig, price))

    # Compute trade P/L
    last_close = float(algo["Close"].iloc[-1])
    tpls = []; pos, ep = "flat", None
    for ts, sig, price in filtered:
        if sig == "BUY":
            if pos == "short" and ep: tpls.append(ep - price)
            pos, ep = "long", price
        elif sig == "SELL":
            if pos == "long" and ep: tpls.append(price - ep)
            pos, ep = "short", price
    if pos != "flat" and ep:
        tpls.append((last_close - ep) if pos == "long" else (ep - last_close))

    if tpls:
        day_pl = sum(tpls)
        total_pl += day_pl
        total_trades += len(tpls)
        winners += sum(1 for p in tpls if p > 0)
        losers += sum(1 for p in tpls if p <= 0)
        daily_pls.append(day_pl)

    done += 1
    print(f"  [{done}/{len(csv_files)}] {int(done/len(csv_files)*100)}%", end="\r", flush=True)

wr = winners / (winners + losers) * 100 if (winners + losers) else 0
usd = total_pl * _CONTRACTS * _MULTIPLIER
avg = np.mean(daily_pls) if daily_pls else 0

print(f"\nDays processed: {done} (excl April 2025)", flush=True)
print(f"Contracts: {_CONTRACTS} x ${_MULTIPLIER}/pt\n", flush=True)
print(f"Total trades: {total_trades}", flush=True)
print(f"Winners: {winners}  Losers: {losers}  Win%: {wr:.1f}%", flush=True)
print(f"Total pts: {total_pl:+.0f}  P/L USD: ${usd:+,.0f}  Avg/day: {avg:+.1f} pts", flush=True)
