"""Interactive chart matching backtest behavior exactly.
Applies: 10-min reversal filter (post-hoc), spike exit, WM shield, partial TP.
Usage: python run_chart.py 2026-02-23 09:30 10:30
"""
import sys, os
import pandas as pd, pytz, numpy as np
import matplotlib
matplotlib.use("TkAgg")
from TradingAlgo import AlgoConfig
from TradingAlgoFast import run_trading_algo_fast
from Plotter import plot_results

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

date = sys.argv[1] if len(sys.argv) > 1 else "2026-02-23"
start_t = sys.argv[2] if len(sys.argv) > 2 else "09:30"
end_t = sys.argv[3] if len(sys.argv) > 3 else "10:30"

fname = os.path.join(_DATA_ROOT, f"CBOT_MINI_YM1_{date}.csv")
df = pd.read_csv(fname, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
ds = pd.Timestamp(f"{date} {start_t}", tz=_EST)
de = pd.Timestamp(f"{date} {end_t}", tz=_EST)
df = df[(df.index >= ds) & (df.index <= de)]

# min_reversal_minutes=0 — backtest applies 10-min filter post-hoc
config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0,
                    max_loss_per_trade=0, line_tolerance=100.0)
algo_df = run_trading_algo_fast(df, date, start_t, end_t, config=config)

# ── Post-hoc backtest filters ────────────────────────────────────────────────
_SPIKE_PTS, _SPIKE_BARS = 100, 5
_WM_TOL, _WM_MT, _WM_MS, _WM_LB, _WM_SHIELD = 12, 4, 15, 30, 12.0
_PARTIAL_TP = 50
_MUL = 5

def find_clusters(vals, times):
    if len(vals) < _WM_MT: return []
    indexed = sorted(zip(vals, times), key=lambda x: x[0])
    clusters, used = [], set()
    for i in range(len(indexed)):
        if i in used: continue
        base = indexed[i][0]; group = [(indexed[i][0], indexed[i][1])]; used.add(i)
        for j in range(i+1, len(indexed)):
            if j in used: continue
            if abs(indexed[j][0]-base) <= _WM_TOL: group.append((indexed[j][0], indexed[j][1])); used.add(j)
            elif indexed[j][0]-base > _WM_TOL: break
        if len(group) >= _WM_MT:
            tt = sorted([g[1] for g in group])
            if (tt[-1]-tt[0]).total_seconds()/60 >= _WM_MS:
                clusters.append((float(np.mean([g[0] for g in group])), len(group)))
    return clusters

# Post-hoc 10-min reversal filter
rows = algo_df[algo_df["signal"].isin(["BUY","SELL"])]
filtered = []
for ts, row in rows.iterrows():
    sig = row["signal"]; price = float(row["buy_price"] if sig=="BUY" else row["sell_price"])
    if not filtered: filtered.append((ts, sig, price)); continue
    lt, ls, _ = filtered[-1]
    if ls != sig and (ts-lt).total_seconds()/60 >= 10: filtered.append((ts, sig, price))
    elif ls == sig: filtered.append((ts, sig, price))

# Replay with spike exit, WM shield, partial TP
closes = algo_df["Close"].values.astype(float)
highs = algo_df["High"].values.astype(float)
lows = algo_df["Low"].values.astype(float)
times = algo_df.index
si = 0; pos = "flat"; ep = None; eb = 0; partial_taken = False; cum_pl = 0.0

algo_df["signal"] = ""
algo_df["buy_price"] = float("nan")
algo_df["sell_price"] = float("nan")
algo_df["pl"] = 0.0
algo_df["position"] = "flat"

for i in range(len(algo_df)):
    if _PARTIAL_TP > 0 and pos != "flat" and ep is not None and not partial_taken:
        unr = (closes[i]-ep) if pos=="long" else (ep-closes[i])
        if unr >= _PARTIAL_TP: cum_pl += unr; partial_taken = True

    if si < len(filtered) and times[i] == filtered[si][0]:
        ts, sig, price = filtered[si]; si += 1
        shielded = False
        if _WM_SHIELD > 0 and pos != "flat" and i >= _WM_LB:
            ws = max(0, i-_WM_LB)
            if pos == "long" and sig == "SELL":
                for lvl, _ in find_clusters(lows[ws:i], times[ws:i]):
                    if lvl < closes[i] and (closes[i]-lvl) <= _WM_SHIELD: shielded = True; break
            elif pos == "short" and sig == "BUY":
                for lvl, _ in find_clusters(highs[ws:i], times[ws:i]):
                    if lvl > closes[i] and (lvl-closes[i]) <= _WM_SHIELD: shielded = True; break
        if not shielded:
            if pos == "long" and sig == "SELL":
                rem = 1 if partial_taken else 2
                cum_pl += (price-ep) * rem
            elif pos == "short" and sig == "BUY":
                rem = 1 if partial_taken else 2
                cum_pl += (ep-price) * rem
            if sig == "BUY":
                algo_df.at[times[i], "signal"] = "BUY"
                algo_df.at[times[i], "buy_price"] = price
                pos, ep, eb = "long", price, i
            else:
                algo_df.at[times[i], "signal"] = "SELL"
                algo_df.at[times[i], "sell_price"] = price
                pos, ep, eb = "short", price, i
            partial_taken = False
        continue

    if pos != "flat" and ep is not None and i > eb:
        if i - eb <= _SPIKE_BARS:
            mv = (closes[i]-ep) if pos=="long" else (ep-closes[i])
            if mv >= _SPIKE_PTS:
                rem = 1 if partial_taken else 2
                cum_pl += mv * rem
                liq_sig = "SELL" if pos=="long" else "BUY"
                algo_df.at[times[i], "signal"] = liq_sig
                if liq_sig == "SELL": algo_df.at[times[i], "sell_price"] = closes[i]
                else: algo_df.at[times[i], "buy_price"] = closes[i]
                pos, ep, eb = "flat", None, 0; partial_taken = False

    if pos != "flat" and ep is not None:
        unr = (closes[i]-ep) if pos=="long" else (ep-closes[i])
        algo_df.at[times[i], "pl"] = cum_pl + unr * (1 if partial_taken else 2)
    else:
        algo_df.at[times[i], "pl"] = cum_pl
    algo_df.at[times[i], "position"] = pos

if pos != "flat" and ep is not None:
    pl = (closes[-1]-ep) if pos=="long" else (ep-closes[-1])
    rem = 1 if partial_taken else 2
    cum_pl += pl * rem
    algo_df.at[times[-1], "pl"] = cum_pl

print(f"Backtest P/L: {cum_pl:.0f} pts  /  ${cum_pl*_MUL:,.0f}")

# Save CSV
csv_dir = os.path.join(os.path.expanduser("~"), "Desktop", "IB_Live", "charts")
os.makedirs(csv_dir, exist_ok=True)
csv_path = os.path.join(csv_dir, f"YM_{date}_{start_t.replace(':','')}_{ end_t.replace(':','')}.csv")
algo_df.to_csv(csv_path)
print(f"CSV saved: {csv_path}")

plot_results(algo_df, date, start_t, end_t)
