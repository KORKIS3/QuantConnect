"""Tolerance sweep with signal count tracking to understand overtrading."""
import os
import pandas as pd, pytz, numpy as np
from TradingAlgo import AlgoConfig
from TradingAlgoFast import run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
csv_files = sorted([f for f in os.listdir(_DATA_ROOT) if f.endswith(".csv")])
print(f"Tolerance sweep (with signal counts) on {len(csv_files)} days\n", flush=True)

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
        for j in range(i + 1, len(indexed)):
            if j in used: continue
            if abs(indexed[j][0] - base) <= _WM_TOL:
                group.append((indexed[j][0], indexed[j][1])); used.add(j)
            elif indexed[j][0] - base > _WM_TOL: break
        if len(group) >= _WM_MT:
            tt = sorted([g[1] for g in group])
            if (tt[-1] - tt[0]).total_seconds() / 60 >= _WM_MS:
                clusters.append((float(np.mean([g[0] for g in group])), len(group)))
    return clusters


def run_bt(algo_df):
    """Returns (day_pts, raw_signal_count, filtered_trade_count)"""
    rows = algo_df[algo_df["signal"].isin(["BUY", "SELL"])]
    raw_signals = len(rows)
    if rows.empty: return None, 0, 0

    # Post-hoc 10-min filter
    filtered = []
    for ts, row in rows.iterrows():
        sig = row["signal"]; price = float(row["buy_price"] if sig == "BUY" else row["sell_price"])
        if not filtered: filtered.append((ts, sig, price)); continue
        lt, ls, _ = filtered[-1]
        if ls != sig and (ts-lt).total_seconds()/60 >= 10: filtered.append((ts, sig, price))
        elif ls == sig: filtered.append((ts, sig, price))
    if not filtered: return None, raw_signals, 0

    closes = algo_df["Close"].values.astype(float)
    highs = algo_df["High"].values.astype(float)
    lows = algo_df["Low"].values.astype(float)
    times = algo_df.index
    si = 0; tpls = []; pos = "flat"; ep = None; eb = 0; partial_taken = False
    trade_count = 0

    for i in range(len(algo_df)):
        if _PARTIAL_TP > 0 and pos != "flat" and ep is not None and not partial_taken:
            unr = (closes[i]-ep) if pos == "long" else (ep-closes[i])
            if unr >= _PARTIAL_TP: tpls.append(unr); partial_taken = True

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
                    for _ in range(rem): tpls.append(price - ep)
                    trade_count += 1
                elif pos == "short" and sig == "BUY":
                    rem = 1 if partial_taken else 2
                    for _ in range(rem): tpls.append(ep - price)
                    trade_count += 1
                if sig == "BUY": pos, ep, eb = "long", price, i
                else: pos, ep, eb = "short", price, i
                partial_taken = False
            continue

        if pos != "flat" and ep is not None and i > eb:
            if i - eb <= _SPIKE_BARS:
                mv = (closes[i]-ep) if pos == "long" else (ep-closes[i])
                if mv >= _SPIKE_PTS:
                    rem = 1 if partial_taken else 2
                    for _ in range(rem): tpls.append(mv)
                    pos, ep, eb = "flat", None, 0; partial_taken = False

    if pos != "flat" and ep is not None:
        pl = (closes[-1]-ep) if pos == "long" else (ep-closes[-1])
        rem = 1 if partial_taken else 2
        for _ in range(rem): tpls.append(pl)

    return (sum(tpls) if tpls else None), raw_signals, trade_count


# Regression baseline is ~3-5 signals/day. Test tolerances that keep signal count reasonable.
tolerances = [100, 150, 200, 300, 500, 750, 1000]

hdr = f"{'Tol':>6} {'Total USD':>14} {'Pts/c/day':>10} {'Win%':>6} {'Sigs/day':>9} {'Trades/day':>11} {'Worst':>10} {'Best':>10}"
print(hdr)
print("-" * len(hdr))

for tol in tolerances:
    config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                        proximity_points=15.0, min_reversal_minutes=0,
                        max_loss_per_trade=0, line_tolerance=float(tol))
    agg_pts = 0.0; daily_pls = []; wins = 0; losses = 0
    total_raw = 0; total_trades = 0; days_counted = 0
    print(f"  Running tol={tol}...", end="", flush=True)
    for fname in csv_files:
        dd = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
        try:
            df = pd.read_csv(os.path.join(_DATA_ROOT, fname), index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        except: continue
        if len(df) < 10: continue
        ds = pd.Timestamp(f"{dd} 09:30", tz=_EST)
        de = pd.Timestamp(f"{dd} 17:00", tz=_EST)
        dd_data = df[(df.index >= ds) & (df.index <= de)]
        if len(dd_data) < 15: continue
        try:
            algo = run_trading_algo_fast(dd_data, dd, "09:30", "17:00", config=config)
        except: continue
        day_pts, raw, trades = run_bt(algo)
        if day_pts is not None:
            agg_pts += day_pts; daily_pls.append(day_pts)
            total_raw += raw; total_trades += trades; days_counted += 1
            if day_pts > 0: wins += 1
            else: losses += 1

    n = len(daily_pls) if daily_pls else 1
    total_usd = agg_pts * _MUL
    avg_pts_cd = agg_pts / 2 / n
    win_pct = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
    avg_sigs = total_raw / days_counted if days_counted else 0
    avg_trades = total_trades / days_counted if days_counted else 0
    worst = min(daily_pls) if daily_pls else 0
    best = max(daily_pls) if daily_pls else 0
    print(f"\r{tol:>6} ${total_usd:>+12,.0f} {avg_pts_cd:>+9.1f} {win_pct:>5.1f}% {avg_sigs:>8.1f} {avg_trades:>10.1f} {worst:>+9.0f} pts {best:>+9.0f} pts", flush=True)

print(f"\nRegression baseline: $+757,105  +143.4 pts/c/day  58.5% win  ~7 trades/day")
print(f"Tol = pts a wick can poke above the line before invalidating that bar as 2nd point.")
