"""Test: ignore same-direction signals vs current behavior (reset entry)."""
import os
import pandas as pd, pytz, numpy as np
from TradingAlgoFast import AlgoConfig
from TradingAlgoFast import run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0,
                    max_loss_per_trade=0, line_tolerance=100.0)
csv_files = sorted([f for f in os.listdir(_DATA_ROOT) if f.endswith(".csv")])
print(f"Same-direction signal test on {len(csv_files)} days\n", flush=True)

_SPIKE_PTS, _SPIKE_BARS = 100, 5
_WM_TOL, _WM_MT, _WM_MS, _WM_LB, _WM_SHIELD = 12, 4, 15, 30, 12.0
_MUL = 5
_PARTIAL_TP = 50

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

def run_bt(algo_df, ignore_same_dir=False):
    rows = algo_df[algo_df["signal"].isin(["BUY","SELL"])]
    if rows.empty: return None
    filtered = []
    for ts, row in rows.iterrows():
        sig = row["signal"]; price = float(row["buy_price"] if sig=="BUY" else row["sell_price"])
        if not filtered: filtered.append((ts, sig, price)); continue
        lt, ls, _ = filtered[-1]
        if ls != sig and (ts-lt).total_seconds()/60 >= 10: filtered.append((ts, sig, price))
        elif ls == sig: filtered.append((ts, sig, price))
    if not filtered: return None

    closes = algo_df["Close"].values.astype(float)
    highs = algo_df["High"].values.astype(float)
    lows = algo_df["Low"].values.astype(float)
    times = algo_df.index
    si = 0; tpls = []; pos = "flat"; ep = None; eb = 0; partial_taken = False

    for i in range(len(algo_df)):
        if _PARTIAL_TP > 0 and pos != "flat" and ep is not None and not partial_taken:
            unr = (closes[i]-ep) if pos=="long" else (ep-closes[i])
            if unr >= _PARTIAL_TP: tpls.append(unr); partial_taken = True

        if si < len(filtered) and times[i] == filtered[si][0]:
            ts, sig, price = filtered[si]; si += 1
            # Skip same-direction signals if ignore_same_dir is True
            if ignore_same_dir and ((pos == "long" and sig == "BUY") or (pos == "short" and sig == "SELL")):
                continue
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
                    for _ in range(rem): tpls.append(price-ep)
                elif pos == "short" and sig == "BUY":
                    rem = 1 if partial_taken else 2
                    for _ in range(rem): tpls.append(ep-price)
                if sig == "BUY": pos, ep, eb = "long", price, i
                else: pos, ep, eb = "short", price, i
                partial_taken = False
            continue

        if pos != "flat" and ep is not None and i > eb:
            if i - eb <= _SPIKE_BARS:
                mv = (closes[i]-ep) if pos=="long" else (ep-closes[i])
                if mv >= _SPIKE_PTS:
                    rem = 1 if partial_taken else 2
                    for _ in range(rem): tpls.append(mv)
                    pos, ep, eb = "flat", None, 0; partial_taken = False

    if pos != "flat" and ep is not None:
        pl = (closes[-1]-ep) if pos=="long" else (ep-closes[-1])
        rem = 1 if partial_taken else 2
        for _ in range(rem): tpls.append(pl)

    return sum(tpls) if tpls else None

for label, ignore in [("Current (reset entry)", False), ("Fixed (ignore same-dir)", True)]:
    agg = 0.0; daily = []; wins = 0; losses = 0
    print(f"Running {label}...", end="", flush=True)
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
        r = run_bt(algo, ignore_same_dir=ignore)
        if r is not None:
            agg += r; daily.append(r)
            if r > 0: wins += 1
            else: losses += 1
    n = len(daily) if daily else 1
    day_wr = wins/(wins+losses)*100 if (wins+losses) else 0
    print(f"\r{label:<30} ${agg*_MUL:>+12,.0f}  {agg/2/n:>+7.1f} pts/c/day  Day%:{day_wr:.1f}%  Worst:{min(daily):.0f}", flush=True)
