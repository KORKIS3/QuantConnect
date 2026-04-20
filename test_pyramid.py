"""Signal-based pyramiding: add contracts on each same-direction signal.
Baseline uses Backtest2Year._filter_and_calc_pl directly (proven correct).
Pyramid variants add contracts on same-dir signals, close all on reversal/spike/EOD."""
import os
import pandas as pd, pytz, numpy as np
from TradingAlgoFast import AlgoConfig
from TradingAlgoFast import run_trading_algo_fast
import Backtest2Year as bt

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0,
                    max_loss_per_trade=0, line_tolerance=100.0)
csv_files = sorted([f for f in os.listdir(_DATA_ROOT) if f.endswith(".csv")])
print(f"Signal-based pyramid test on {len(csv_files)} days\n", flush=True)

_SPIKE_PTS, _SPIKE_BARS = 100, 5
_WM_LOOKBACK = 30; _WM_SHIELD = 12.0
_MUL = 5; _PARTIAL_TP = 50; _BASE = 2


def run_pyramid(algo_df, start_ts, end_ts, add_per_signal):
    """Pyramid variant: add add_per_signal contracts on each same-direction signal."""
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

    closes = sliced["Close"].values.astype(float)
    highs = sliced["High"].values.astype(float)
    lows = sliced["Low"].values.astype(float)
    times = sliced.index
    si = 0; total_pts = 0.0; pos = "flat"; entry_bar = 0
    partial_taken = False
    # entries: list of (entry_price, num_contracts)
    entries = []

    def cur_contracts():
        return sum(c for _, c in entries)

    def close_all(exit_price):
        nonlocal pos, entry_bar, partial_taken, total_pts
        for ep, c in entries:
            pl = (exit_price - ep) if pos == "long" else (ep - exit_price)
            total_pts += pl * c
        entries.clear()
        pos = "flat"; entry_bar = 0; partial_taken = False

    for i in range(len(sliced)):
        # Partial TP: take profit on 1 contract from base entry when +50pts
        if _PARTIAL_TP > 0 and pos != "flat" and entries and not partial_taken:
            base_ep = entries[0][0]
            unr = (closes[i]-base_ep) if pos=="long" else (base_ep-closes[i])
            if unr >= _PARTIAL_TP:
                total_pts += unr * 1  # 1 contract partial
                if entries[0][1] > 1:
                    entries[0] = (entries[0][0], entries[0][1]-1)
                else:
                    entries.pop(0)
                partial_taken = True

        if si < len(filtered) and times[i] == filtered[si][0]:
            ts, sig, price = filtered[si]; si += 1
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
                same_dir = (pos=="long" and sig=="BUY") or (pos=="short" and sig=="SELL")
                if same_dir:
                    # Add contracts at new price
                    entries.append((price, add_per_signal))
                else:
                    # Reversal or new entry from flat
                    if pos != "flat":
                        close_all(price)
                    entries.append((price, _BASE))
                    pos = "long" if sig=="BUY" else "short"
                    entry_bar = i
                    partial_taken = False
            continue

        # Spike exit (on base entry)
        if pos != "flat" and entries and i > entry_bar:
            base_ep = entries[0][0]
            if i - entry_bar <= _SPIKE_BARS:
                mv = (closes[i]-base_ep) if pos=="long" else (base_ep-closes[i])
                if mv >= _SPIKE_PTS:
                    close_all(closes[i])

    if pos != "flat" and entries:
        close_all(closes[-1])

    return total_pts if total_pts != 0.0 else None


hdr = f"{'Label':<28} {'Total USD':>14} {'Pts/c/day':>10} {'Day%':>6} {'Worst':>10} {'Best':>10}"
print(hdr)
print("-" * len(hdr))

# Baseline: use proven _filter_and_calc_pl
for label, fn in [
    ("Baseline (proven)", None),
    ("Add 1c per signal", 1),
    ("Add 2c per signal", 2),
]:
    agg = 0.0; daily = []; wins = 0; losses = 0
    print(f"  Running {label}...", end="", flush=True)
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

        if fn is None:
            tpls = bt._filter_and_calc_pl(algo, ds, de, partial_tp_pts=50)
            r = sum(tpls) if tpls else None
        else:
            r = run_pyramid(algo, ds, de, add_per_signal=fn)

        if r is not None:
            agg += r; daily.append(r)
            if r > 0: wins += 1
            else: losses += 1

    n = len(daily) if daily else 1
    day_wr = wins/(wins+losses)*100 if (wins+losses) else 0
    total_usd = agg * _MUL
    avg_pts = agg / _BASE / n
    worst = min(daily) if daily else 0
    best = max(daily) if daily else 0
    print(f"\r{label:<28} ${total_usd:>+12,.0f} {avg_pts:>+9.1f} {day_wr:>5.1f}% {worst:>+9.0f} pts {best:>+9.0f} pts", flush=True)
