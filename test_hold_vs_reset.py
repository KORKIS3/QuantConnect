"""Prove: holding through same-direction signals = close-and-reopen (same P/L).
Uses Backtest2Year._filter_and_calc_pl as the reference (reset entry = $1.38M).
Then implements a clean 'hold' version that ignores same-dir signals."""
import os
import pandas as pd, pytz, numpy as np
from TradingAlgo import AlgoConfig
from TradingAlgoFast import run_trading_algo_fast
import Backtest2Year as bt

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0,
                    max_loss_per_trade=0, line_tolerance=100.0)
csv_files = sorted([f for f in os.listdir(_DATA_ROOT) if f.endswith(".csv")])
print(f"Hold vs Reset test on {len(csv_files)} days\n", flush=True)

_SPIKE_PTS, _SPIKE_BARS = 100, 5
_WM_LOOKBACK = 30; _WM_SHIELD = 12.0
_MUL = 5; _PARTIAL_TP = 50; _BASE = 2


def run_hold(algo_df, start_ts, end_ts):
    """Hold through same-direction signals. Only act on reversals, spike exits, and EOD.
    Partial TP still applies on the original entry."""
    sliced = algo_df[(algo_df.index >= start_ts) & (algo_df.index <= end_ts)]
    if len(sliced) < 2: return None
    rows = sliced[sliced["signal"].isin(["BUY","SELL"])]
    if rows.empty: return None

    # 10-min filter
    filtered = []
    for ts, row in rows.iterrows():
        sig = row["signal"]; price = float(row["buy_price"] if sig=="BUY" else row["sell_price"])
        if not filtered: filtered.append((ts, sig, price)); continue
        lt, ls, _ = filtered[-1]
        if ls != sig and (ts-lt).total_seconds()/60 >= 10: filtered.append((ts, sig, price))
        elif ls == sig: filtered.append((ts, sig, price))
    if not filtered: return None

    # Remove same-direction signals — only keep reversals and first entry
    hold_filtered = []
    for ts, sig, price in filtered:
        if not hold_filtered:
            hold_filtered.append((ts, sig, price))
        elif hold_filtered[-1][1] != sig:
            hold_filtered.append((ts, sig, price))
        # else: same direction — skip (hold)

    if not hold_filtered: return None

    closes = sliced["Close"].values.astype(float)
    highs = sliced["High"].values.astype(float)
    lows = sliced["Low"].values.astype(float)
    times = sliced.index
    si = 0; tpls = []; pos = "flat"; ep = None; entry_bar = 0
    partial_taken = False

    for i in range(len(sliced)):
        # Partial TP
        if _PARTIAL_TP > 0 and pos != "flat" and ep is not None and not partial_taken:
            unr = (closes[i]-ep) if pos=="long" else (ep-closes[i])
            if unr >= _PARTIAL_TP:
                tpls.append(unr)
                partial_taken = True

        if si < len(hold_filtered) and times[i] == hold_filtered[si][0]:
            ts, sig, price = hold_filtered[si]; si += 1
            shielded = False
            if _WM_SHIELD > 0 and pos != "flat" and i >= _WM_LOOKBACK:
                ws = max(0, i-_WM_LOOKBACK)
                if pos == "long" and sig == "SELL":
                    for lvl, _ in bt._find_wm_clusters(lows[ws:i], times[ws:i]):
                        if lvl < closes[i] and (closes[i]-lvl) <= _WM_SHIELD: shielded = True; break
                elif pos == "short" and sig == "BUY":
                    for lvl, _ in bt._find_wm_clusters(highs[ws:i], times[ws:i]):
                        if lvl > closes[i] and (lvl-closes[i]) <= _WM_SHIELD: shielded = True; break
            if not shielded:
                if pos == "long" and sig == "SELL":
                    rem = 1 if partial_taken else 2
                    for _ in range(rem): tpls.append(price - ep)
                elif pos == "short" and sig == "BUY":
                    rem = 1 if partial_taken else 2
                    for _ in range(rem): tpls.append(ep - price)
                if sig == "BUY": pos, ep, entry_bar = "long", price, i
                else: pos, ep, entry_bar = "short", price, i
                partial_taken = False
            continue

        # Spike exit
        if pos != "flat" and ep is not None and i > entry_bar:
            if i - entry_bar <= _SPIKE_BARS:
                mv = (closes[i]-ep) if pos=="long" else (ep-closes[i])
                if mv >= _SPIKE_PTS:
                    rem = 1 if partial_taken else 2
                    for _ in range(rem): tpls.append(mv)
                    pos, ep, entry_bar = "flat", None, 0; partial_taken = False

    if pos != "flat" and ep is not None:
        pl = (closes[-1]-ep) if pos=="long" else (ep-closes[-1])
        rem = 1 if partial_taken else 2
        for _ in range(rem): tpls.append(pl)

    return sum(tpls) if tpls else None


# Run both methods
results = {"Backtest2Year (reset entry)": [], "Hold (ignore same-dir)": []}

print("Running both methods...", flush=True)
for fname in csv_files:
    dd = fname.replace("CBOT_MINI_YM1_","").replace(".csv","")
    try:
        df = pd.read_csv(os.path.join(_DATA_ROOT, fname), index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    except: continue
    ds = pd.Timestamp(f"{dd} 09:30", tz=_EST); de = pd.Timestamp(f"{dd} 17:00", tz=_EST)
    dd_data = df[(df.index >= ds) & (df.index <= de)]
    if len(dd_data) < 15: continue
    try: algo = run_trading_algo_fast(dd_data, dd, "09:30", "17:00", config=config)
    except: continue

    tpls = bt._filter_and_calc_pl(algo, ds, de, partial_tp_pts=50)
    r1 = sum(tpls) if tpls else None
    r2 = run_hold(algo, ds, de)

    if r1 is not None: results["Backtest2Year (reset entry)"].append(r1)
    if r2 is not None: results["Hold (ignore same-dir)"].append(r2)

print(f"\n{'Method':<35} {'Total USD':>14} {'Pts/c/day':>10} {'Day%':>6}")
print("-" * 70)
for label, daily in results.items():
    n = len(daily) if daily else 1
    agg = sum(daily)
    wins = sum(1 for x in daily if x > 0)
    day_wr = wins/n*100
    print(f"{label:<35} ${agg*_MUL:>+12,.0f} {agg/_BASE/n:>+9.1f} {day_wr:>5.1f}%")

print("\nIf the math is correct, both should show ~$1,384,985")
