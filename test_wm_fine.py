"""Fine-tune water mark shield below 20pts."""
import os
import pandas as pd, pytz, numpy as np
from TradingAlgoFast import AlgoConfig
from TradingAlgoFast import run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0, max_loss_per_trade=0,
                    confirmation_bars=0)

csv_files = sorted([f for f in os.listdir(_DATA_ROOT) if f.endswith(".csv")])
print(f"Fine-tune shield test on {len(csv_files)} days...\n", flush=True)

_SPIKE_PTS = 100
_SPIKE_BARS = 5
WM_TOLERANCE = 12
WM_MIN_TOUCHES = 4
WM_MIN_SPAN = 15
WM_LOOKBACK = 30


def find_clusters(vals, times, tol, mt, ms):
    if len(vals) < mt:
        return []
    indexed = sorted(zip(vals, times), key=lambda x: x[0])
    clusters = []
    used = set()
    for i in range(len(indexed)):
        if i in used:
            continue
        base = indexed[i][0]
        group = [(indexed[i][0], indexed[i][1])]
        used.add(i)
        for j in range(i + 1, len(indexed)):
            if j in used:
                continue
            if abs(indexed[j][0] - base) <= tol:
                group.append((indexed[j][0], indexed[j][1]))
                used.add(j)
            elif indexed[j][0] - base > tol:
                break
        if len(group) >= mt:
            tt = sorted([g[1] for g in group])
            span = (tt[-1] - tt[0]).total_seconds() / 60
            if span >= ms:
                clusters.append((np.mean([g[0] for g in group]), len(group)))
    return clusters


def run_backtest(algo_df, shield_dist):
    rows = algo_df[algo_df["signal"].isin(["BUY", "SELL"])]
    if rows.empty:
        return None
    filtered = []
    for ts, row in rows.iterrows():
        sig = row["signal"]
        price = float(row["buy_price"] if sig == "BUY" else row["sell_price"])
        if not filtered:
            filtered.append((ts, sig, price)); continue
        lt, ls, _ = filtered[-1]
        if ls != sig:
            if (ts - lt).total_seconds() / 60 >= 10:
                filtered.append((ts, sig, price))
        else:
            filtered.append((ts, sig, price))
    if not filtered:
        return None

    closes = algo_df["Close"].values.astype(float)
    highs = algo_df["High"].values.astype(float)
    lows = algo_df["Low"].values.astype(float)
    times = algo_df.index
    si = 0; tpls = []; pos = "flat"; ep = None; eb = 0; shd = 0

    for i in range(len(algo_df)):
        if si < len(filtered) and times[i] == filtered[si][0]:
            ts, sig, price = filtered[si]; si += 1
            act = True
            if shield_dist > 0 and pos != "flat" and i >= WM_LOOKBACK:
                ws = max(0, i - WM_LOOKBACK)
                if pos == "long" and sig == "SELL":
                    for lvl, _ in find_clusters(lows[ws:i], times[ws:i], WM_TOLERANCE, WM_MIN_TOUCHES, WM_MIN_SPAN):
                        if lvl < closes[i] and (closes[i] - lvl) <= shield_dist:
                            act = False; shd += 1; break
                elif pos == "short" and sig == "BUY":
                    for lvl, _ in find_clusters(highs[ws:i], times[ws:i], WM_TOLERANCE, WM_MIN_TOUCHES, WM_MIN_SPAN):
                        if lvl > closes[i] and (lvl - closes[i]) <= shield_dist:
                            act = False; shd += 1; break
            if act:
                if pos == "long" and sig == "SELL": tpls.append(price - ep)
                elif pos == "short" and sig == "BUY": tpls.append(ep - price)
                if sig == "BUY": pos, ep, eb = "long", price, i
                else: pos, ep, eb = "short", price, i
            continue
        if pos != "flat" and ep is not None and i > eb:
            bh = i - eb
            if bh <= _SPIKE_BARS:
                mv = (closes[i] - ep) if pos == "long" else (ep - closes[i])
                if mv >= _SPIKE_PTS:
                    tpls.append(mv); pos, ep, eb = "flat", None, 0
    if pos != "flat" and ep is not None:
        lc = closes[-1]
        tpls.append((lc - ep) if pos == "long" else (ep - lc))
    return (tpls, shd) if tpls else None


distances = [0, 10, 12, 15, 18]
for dist in distances:
    tp = 0.0; tt = 0; w = 0; l = 0; dp = []; ts_count = 0
    for fname in csv_files:
        dd = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
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
        r = run_backtest(algo, dist)
        if r:
            tpls, s = r
            if tpls:
                dpl = sum(tpls); tp += dpl; tt += len(tpls)
                w += sum(1 for p in tpls if p > 0); l += sum(1 for p in tpls if p <= 0)
                dp.append(dpl); ts_count += s
    wr = w / (w + l) * 100 if (w + l) else 0
    usd = tp * 2 * 5; avg = np.mean(dp) if dp else 0
    lb = f"SHIELD {dist}pts" if dist > 0 else "BASELINE"
    print(f"{lb:<16} Trades:{tt:>5}  Win%:{wr:>5.1f}%  Pts:{tp:>+8.0f}  ${usd:>+10,.0f}  Avg:{avg:>+6.1f}/day  Shields:{ts_count}", flush=True)
