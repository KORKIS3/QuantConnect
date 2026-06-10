"""Test old engine (from 265/day commit) with honest P/L calculation.

Uses the SAME post-hoc filter + 60pt SL that Engine 89 uses.
No double-counting. Every trade: (exit - entry) * contracts.
"""
import os, sys, importlib.util
import pandas as pd
import numpy as np
import pytz

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

# Load old engine from file
spec = importlib.util.spec_from_file_location("old_engine", "TradingAlgoFast_old.py")
old_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old_mod)

OldAlgoConfig = old_mod.AlgoConfig
old_run = old_mod.run_trading_algo_fast

# Old config that produced 265/day
config = OldAlgoConfig(
    warmup_minutes=12,
    steep_angle_threshold=70.0,
    proximity_points=15.0,
    min_reversal_minutes=0,
    max_loss_per_trade=0,
)

STOP_LOSS = 60
PARTIAL_TP = 50

csv_files = sorted([f for f in os.listdir(_DATA_ROOT)
                    if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])

daily_pls = []
all_trades = []

for idx, fname in enumerate(csv_files):
    target_date = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
    fpath = os.path.join(_DATA_ROOT, fname)

    try:
        df = pd.read_csv(fpath, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        if len(df) < 15:
            continue
        if (df[["Open", "High", "Low", "Close"]] <= 0).any().any():
            continue
        if df["High"].max() == df["Low"].min():
            continue
        if df["Volume"].sum() < 100:
            continue

        day_start = pd.Timestamp(f"{target_date} 09:30", tz=_EST)
        day_end = pd.Timestamp(f"{target_date} 16:59", tz=_EST)
        day_data = df[(df.index >= day_start) & (df.index <= day_end)]
        if len(day_data) < 15:
            continue

        algo_df = old_run(day_data, target_date, "09:30", "17:00", config=config)

        end_ts = pd.Timestamp(f"{target_date} 17:00", tz=_EST)
        sliced = algo_df[(algo_df.index >= day_start) & (algo_df.index <= end_ts)]
        if len(sliced) < 2:
            continue

        rows = sliced[sliced["signal"].isin(["BUY", "SELL"])]
        if rows.empty:
            continue

        # Post-hoc 10-min reversal filter
        filtered = []
        for ts, row in rows.iterrows():
            sig = row["signal"]
            price = float(row["buy_price"] if sig == "BUY" else row["sell_price"])
            if not filtered:
                filtered.append((ts, sig, price))
                continue
            last_ts, last_sig, _ = filtered[-1]
            if last_sig != sig:
                if (ts - last_ts).total_seconds() / 60 >= 10:
                    filtered.append((ts, sig, price))
            else:
                filtered.append((ts, sig, price))

        if not filtered:
            continue

        # HONEST P/L replay: 2 contracts, partial TP at 50, hard SL at 60
        closes = sliced["Close"].values.astype(float)
        highs = sliced["High"].values.astype(float)
        lows = sliced["Low"].values.astype(float)
        times = sliced.index
        sig_idx = 0
        total_pl = 0.0
        pos = "flat"
        ep = None
        partial_taken = False
        contracts = 2

        for i in range(len(sliced)):
            if pos != "flat" and ep is not None:
                # Hard stop loss check (on High/Low)
                if pos == "long":
                    adverse = ep - lows[i]
                else:
                    adverse = highs[i] - ep

                if STOP_LOSS > 0 and adverse >= STOP_LOSS:
                    # Stopped out: lose STOP_LOSS per remaining contract
                    remaining = 1 if partial_taken else 2
                    total_pl += -STOP_LOSS * remaining
                    pos = "flat"
                    ep = None
                    partial_taken = False
                    contracts = 2
                    continue

                # Partial TP check
                unrealized = (closes[i] - ep) if pos == "long" else (ep - closes[i])
                if not partial_taken and unrealized >= PARTIAL_TP:
                    # Close 1 contract at +50 pts profit
                    total_pl += PARTIAL_TP
                    partial_taken = True
                    contracts = 1

            # Signal check
            if sig_idx < len(filtered) and times[i] == filtered[sig_idx][0]:
                ts_sig, sig, price = filtered[sig_idx]
                sig_idx += 1

                # Close existing position at signal price
                if pos == "long" and sig == "SELL":
                    pl_per_contract = price - ep
                    remaining = 1 if partial_taken else 2
                    total_pl += pl_per_contract * remaining
                elif pos == "short" and sig == "BUY":
                    pl_per_contract = ep - price
                    remaining = 1 if partial_taken else 2
                    total_pl += pl_per_contract * remaining

                # Open new position
                if sig == "BUY":
                    pos, ep = "long", price
                else:
                    pos, ep = "short", price
                partial_taken = False
                contracts = 2

        # Close at session end
        if pos != "flat" and ep is not None:
            final_close = closes[-1]
            if pos == "long":
                pl_per_contract = final_close - ep
            else:
                pl_per_contract = ep - final_close
            remaining = 1 if partial_taken else 2
            total_pl += pl_per_contract * remaining

        if total_pl != 0.0:
            daily_pls.append(total_pl)

    except Exception as exc:
        continue

    if (idx + 1) % 100 == 0:
        print(f"  [{idx+1}/{len(csv_files)}] {len(daily_pls)} days...", flush=True)

# Results
arr = np.array(daily_pls)
win_days = (arr > 0).sum()
lose_days = (arr <= 0).sum()

print(f"\n{'='*60}", flush=True)
print(f"OLD ENGINE + HONEST P/L + 60pt SL + Partial TP @50", flush=True)
print(f"{'='*60}", flush=True)
print(f"Days with results: {len(arr)}", flush=True)
print(f"Win days: {win_days} ({win_days/len(arr)*100:.1f}%)", flush=True)
print(f"Lose days: {lose_days} ({lose_days/len(arr)*100:.1f}%)", flush=True)
print(f"Total pts: {arr.sum():.0f}", flush=True)
print(f"Avg pts/day: {arr.mean():.1f}", flush=True)
print(f"Median pts/day: {np.median(arr):.1f}", flush=True)
print(f"Std dev: {arr.std():.1f}", flush=True)
print(f"Best day: {arr.max():.0f}", flush=True)
print(f"Worst day: {arr.min():.0f}", flush=True)
print(f"Max drawdown: {(np.cumsum(arr) - np.maximum.accumulate(np.cumsum(arr))).min():.0f}", flush=True)
