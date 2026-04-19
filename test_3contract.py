"""3-contract partial TP: sell 1st at X pts, sell 2nd at Y pts, hold 3rd per system.
Day session only, 2-year backtest."""
import os
import pandas as pd, pytz, numpy as np
from TradingAlgo import AlgoConfig
from TradingAlgoFast import run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0, max_loss_per_trade=0)
csv_files = sorted([f for f in os.listdir(_DATA_ROOT) if f.endswith(".csv")])
print(f"3-contract test on {len(csv_files)} days (day session)...\n", flush=True)

_SPIKE_PTS, _SPIKE_BARS = 100, 5
_WM_TOL, _WM_MT, _WM_MS, _WM_LB, _WM_SHIELD = 12, 4, 15, 30, 12.0
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
            if abs(indexed[j][0] - base) <= _WM_TOL: group.append((indexed[j][0], indexed[j][1])); used.add(j)
            elif indexed[j][0] - base > _WM_TOL: break
        if len(group) >= _WM_MT:
            tt = sorted([g[1] for g in group])
            if (tt[-1]-tt[0]).total_seconds()/60 >= _WM_MS:
                clusters.append((float(np.mean([g[0] for g in group])), len(group)))
    return clusters


def run_bt(algo_df, tp1, tp2):
    """3 contracts: TP1 on 1st, TP2 on 2nd, hold 3rd. tp1=0 means baseline (all 3 held)."""
    rows = algo_df[algo_df["signal"].isin(["BUY","SELL"])]
    if rows.empty: return None
    filtered = []
    for ts, row in rows.iterrows():
        sig = row["signal"]; price = float(row["buy_price"] if sig == "BUY" else row["sell_price"])
        if not filtered: filtered.append((ts, sig, price)); continue
        lt, ls, _ = filtered[-1]
        if ls != sig and (ts-lt).total_seconds()/60 >= 10: filtered.append((ts, sig, price))
        elif ls == sig: filtered.append((ts, sig, price))
    if not filtered: return None

    closes = algo_df["Close"].values.astype(float)
    highs = algo_df["High"].values.astype(float)
    lows = algo_df["Low"].values.astype(float)
    times = algo_df.index
    si = 0; tpls = []; pos = "flat"; ep = None; eb = 0
    tp1_taken = False; tp2_taken = False

    for i in range(len(algo_df)):
        # Partial TPs
        if pos != "flat" and ep is not None:
            unr = (closes[i]-ep) if pos == "long" else (ep-closes[i])
            if tp1 > 0 and not tp1_taken and unr >= tp1:
                tpls.append(unr); tp1_taken = True
            if tp2 > 0 and not tp2_taken and tp1_taken and unr >= tp2:
                tpls.append(unr); tp2_taken = True

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
                    pl = price - ep
                    remaining = 3 - (1 if tp1_taken else 0) - (1 if tp2_taken else 0)
                    for _ in range(remaining): tpls.append(pl)
                elif pos == "short" and sig == "BUY":
                    pl = ep - price
                    remaining = 3 - (1 if tp1_taken else 0) - (1 if tp2_taken else 0)
                    for _ in range(remaining): tpls.append(pl)
                if sig == "BUY": pos, ep, eb = "long", price, i
                else: pos, ep, eb = "short", price, i
                tp1_taken = False; tp2_taken = False
            continue

        if pos != "flat" and ep is not None and i > eb:
            if i - eb <= _SPIKE_BARS:
                mv = (closes[i]-ep) if pos == "long" else (ep-closes[i])
                if mv >= _SPIKE_PTS:
                    remaining = 3 - (1 if tp1_taken else 0) - (1 if tp2_taken else 0)
                    for _ in range(remaining): tpls.append(mv)
                    pos, ep, eb = "flat", None, 0; tp1_taken = False; tp2_taken = False

    if pos != "flat" and ep is not None:
        pl = (closes[-1]-ep) if pos == "long" else (ep-closes[-1])
        remaining = 3 - (1 if tp1_taken else 0) - (1 if tp2_taken else 0)
        for _ in range(remaining): tpls.append(pl)
    return tpls if tpls else None


# Test combos: (tp1, tp2, label)
combos = [
    (0, 0, "BASELINE 3c (no TP)"),
    (20, 50, "TP1@20 TP2@50"),
    (20, 70, "TP1@20 TP2@70"),
    (25, 50, "TP1@25 TP2@50"),
    (25, 70, "TP1@25 TP2@70"),
    (30, 50, "TP1@30 TP2@50"),
    (30, 70, "TP1@30 TP2@70"),
    (30, 100, "TP1@30 TP2@100"),
]

for tp1, tp2, label in combos:
    total_usd = 0.0; trades = 0; daily = []
    for fname in csv_files:
        dd = fname.replace("CBOT_MINI_YM1_","").replace(".csv","")
        try:
            df = pd.read_csv(os.path.join(_DATA_ROOT, fname), index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        except: continue
        if len(df) < 10: continue
        ds = pd.Timestamp(f"{dd} 09:30", tz=_EST)
        de = pd.Timestamp(f"{dd} 16:59", tz=_EST)
        dd_data = df[(df.index >= ds) & (df.index <= de)]
        if len(dd_data) < 15: continue
        try: algo = run_trading_algo_fast(dd_data, dd, "09:30", "17:00", config=config)
        except: continue
        tpls = run_bt(algo, tp1, tp2)
        if tpls:
            usd = sum(tpls) * _MUL
            total_usd += usd; trades += len(tpls); daily.append(usd)
    n = len(daily) if daily else 1
    avg_pts = total_usd / _MUL / 3 / n  # pts per contract per day
    print(f"{label:<24} ${total_usd:>+11,.0f}  Avg:{avg_pts:>+6.1f} pts/c/day  Trades:{trades}", flush=True)
