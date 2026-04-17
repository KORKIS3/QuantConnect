"""Quick backtest against 930_1130 data to reproduce proven 52% win rate."""
import os, sys, time as tm
import pandas as pd, pytz, numpy as np
from TradingAlgo import AlgoConfig
from TradingAlgoFast import run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1130")
_CONTRACTS = 2
_MULTIPLIER = 5

END_TIMES = ["full"]

config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0, max_loss_per_trade=0)

csv_files = sorted([f for f in os.listdir(_DATA_ROOT) if f.endswith(".csv")])
print(f"Running backtest on {len(csv_files)} days (930_1130 data)...\n", flush=True)

totals = {et: {"trades":0,"pl":0.0,"winners":0,"losers":0,"daily_pls":[]} for et in END_TIMES}
done = 0

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

    start_ts = df.index[0]
    end_ts = df.index[-1]
    sliced = algo
    if len(sliced) < 2: done += 1; continue
    rows = sliced[sliced["signal"].isin(["BUY","SELL"])]
    if rows.empty: done += 1; continue
    trades = [(ts, row["signal"], float(row["buy_price"] if row["signal"]=="BUY" else row["sell_price"]))
              for ts, row in rows.iterrows()]
    last_close = float(sliced["Close"].iloc[-1])
    tpls = []; pos, ep = "flat", None
    for ts, sig, price in trades:
        if sig == "BUY":
            if pos == "short" and ep: tpls.append(ep - price)
            pos, ep = "long", price
        elif sig == "SELL":
            if pos == "long" and ep: tpls.append(price - ep)
            pos, ep = "short", price
    if pos != "flat" and ep:
        tpls.append((last_close - ep) if pos == "long" else (ep - last_close))
    if tpls:
        et = "full"
        day_pl = sum(tpls)
        totals[et]["trades"] += len(tpls)
        totals[et]["pl"] += day_pl
        totals[et]["winners"] += sum(1 for p in tpls if p > 0)
        totals[et]["losers"] += sum(1 for p in tpls if p <= 0)
        totals[et]["daily_pls"].append(day_pl)

    done += 1
    print(f"  [{done}/{len(csv_files)}] {int(done/len(csv_files)*100)}%", end="\r", flush=True)

print(f"\nDays processed: {done}", flush=True)
print(f"Contracts:      {_CONTRACTS} x ${_MULTIPLIER}/pt\n", flush=True)
print(f"{'End Time':<12} {'Trades':>7} {'Win':>8} {'Lose':>7} {'Win%':>6} {'Pts':>10} {'P/L USD':>12} {'Avg/Day':>8}", flush=True)
print("-" * 80, flush=True)
for et in END_TIMES:
    t = totals[et]
    tr = t["trades"]; wr = t["winners"]/tr*100 if tr else 0
    usd = t["pl"]*_CONTRACTS*_MULTIPLIER; avg = np.mean(t["daily_pls"]) if t["daily_pls"] else 0
    print(f"{et:<12} {tr:>7} {t['winners']:>8} {t['losers']:>7} {wr:>5.1f}% {t['pl']:>10.0f} ${usd:>11,.0f} {avg:>+7.1f}", flush=True)
print(flush=True)
