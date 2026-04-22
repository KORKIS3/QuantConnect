"""Sweep trailing stop activation threshold."""
import os, pandas as pd, pytz, numpy as np
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig
from Backtest2Year import _filter_and_calc_pl

_EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
csv_files = sorted([f for f in os.listdir(DATA_ROOT) if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])

# We need to modify the activation threshold — it's hardcoded as 75 in _run_signals_nb
# So we'll test by running the full backtest with different values
# For now just test on the 930_1000 data quickly

DATA_930 = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1000")
files_930 = sorted([f for f in os.listdir(DATA_930) if f.endswith(".csv")])

print("Testing trailing stop activation on 930_1000 data (quick)...")
print("NOTE: activation threshold is hardcoded at 75 in _run_signals_nb")
print("This test uses the backtest post-hoc filter which doesn't change it.")
print()
print("The question is: does the 75pt threshold match what was proven optimal?")
print()

# Check the steering doc reference
print("From steering doc: trailing stop v3 activates at 75pts")
print("Previous test showed: +$116,490 with trailing stop v3")
print()
print("The 13:13 short on 04/21 only reached +53pts max profit")
print("before bouncing — so ANY activation threshold > 53 would miss it.")
print()
print("Lowering to 50pts would catch it, but would also trigger")
print("on many normal pullbacks that currently recover.")
print()

# Quick test: how often does a trade reach 50-75pts then reverse vs recover?
total = 0; reached_50 = 0; reached_75 = 0; reversed_50_75 = 0

for fname in files_930[:200]:
    date = fname.replace("CBOT_MINI_YM1_","").replace(".csv","")
    df = pd.read_csv(os.path.join(DATA_930, fname), index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    if len(df) < 10: continue
    cfg = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                     proximity_points=15.0, min_reversal_minutes=10, min_entry_angle=30.0)
    try:
        r = run_trading_algo_fast(df, date, "09:30", "10:30", config=cfg)
    except: continue

    sigs = r[r["signal"].isin(["BUY","SELL"])]
    if sigs.empty: continue

    # For each trade, track max unrealized and final result
    pos = "flat"; ep = None; max_unreal = 0
    for ts, row in r.iterrows():
        if row["signal"] in ["BUY","SELL"]:
            if pos != "flat" and ep is not None:
                final_unreal = (float(row["buy_price"] if row["signal"]=="BUY" else row["sell_price"]) - ep) if pos == "long" else (ep - float(row["buy_price"] if row["signal"]=="BUY" else row["sell_price"]))
                total += 1
                if max_unreal >= 50: reached_50 += 1
                if max_unreal >= 75: reached_75 += 1
                if max_unreal >= 50 and max_unreal < 75 and final_unreal < 0:
                    reversed_50_75 += 1
            pos = "long" if row["signal"]=="BUY" else "short"
            ep = float(row["buy_price"] if row["signal"]=="BUY" else row["sell_price"])
            max_unreal = 0
        elif pos != "flat" and ep is not None:
            unreal = (float(row["Close"]) - ep) if pos == "long" else (ep - float(row["Close"]))
            if unreal > max_unreal: max_unreal = unreal

print(f"Trades analyzed: {total}")
print(f"Reached 50pts profit: {reached_50} ({reached_50/total*100:.1f}%)")
print(f"Reached 75pts profit: {reached_75} ({reached_75/total*100:.1f}%)")
print(f"Reached 50-75pts then reversed to loss: {reversed_50_75} ({reversed_50_75/max(reached_50,1)*100:.1f}% of 50pt trades)")
print()
print("If we lower threshold to 50pts, we'd activate trailing stop on")
print(f"{reached_50-reached_75} additional trades that currently don't get it.")
print(f"Of those, {reversed_50_75} reversed to a loss — those would benefit.")
