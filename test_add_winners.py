"""Add-to-winners test with two approaches:
A) No partial TP, add contracts at profit intervals (pure pyramid)
B) Sell half at 50pts, then add contracts starting at higher threshold (layered)
Day session only (9:30-17:00), 2-year backtest."""
import os
import pandas as pd, pytz, numpy as np
from TradingAlgo import AlgoConfig
from TradingAlgoFast import run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0, max_loss_per_trade=0)
csv_files = sorted([f for f in os.listdir(_DATA_ROOT) if f.endswith(".csv")])
print(f"Add-to-winners test on {len(csv_files)} days (day session 9:30-17:00)\n", flush=True)

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


def run_bt(algo_df, partial_tp, add_start, add_interval):
    """Replay day session.
    partial_tp: pts to sell half at (0=disabled, 50=current strategy)
    add_start: unrealized profit from entry to trigger first add (0=disabled)
    add_interval: add another contract every X pts beyond add_start
    """
    rows = algo_df[algo_df["signal"].isin(["BUY", "SELL"])]
    if rows.empty: return None

    # Post-hoc 10-min reversal filter
    filtered = []
    for ts, row in rows.iterrows():
        sig = row["signal"]
        price = float(row["buy_price"] if sig == "BUY" else row["sell_price"])
        if not filtered:
            filtered.append((ts, sig, price)); continue
        lt, ls, _ = filtered[-1]
        if ls != sig and (ts - lt).total_seconds() / 60 >= 10:
            filtered.append((ts, sig, price))
        elif ls == sig:
            filtered.append((ts, sig, price))
    if not filtered: return None

    closes = algo_df["Close"].values.astype(float)
    highs = algo_df["High"].values.astype(float)
    lows = algo_df["Low"].values.astype(float)
    times = algo_df.index

    si = 0
    tpls = []
    pos = "flat"; ep = None; eb = 0
    partial_taken = False
    added = []         # entry prices for added contracts
    max_c = 2; next_add_lvl = 0
    total_adds = 0

    def close_position(exit_price):
        nonlocal pos, ep, eb, partial_taken, added, next_add_lvl
        base_remaining = 1 if partial_taken else 2
        base_pl = (exit_price - ep) if pos == "long" else (ep - exit_price)
        for _ in range(base_remaining):
            tpls.append(base_pl)
        for ap in added:
            tpls.append((exit_price - ap) if pos == "long" else (ap - exit_price))
        added = []; next_add_lvl = 0
        pos, ep, eb = "flat", None, 0
        partial_taken = False

    for i in range(len(algo_df)):
        # 1) Partial take-profit
        if partial_tp > 0 and pos != "flat" and ep is not None and not partial_taken:
            unr = (closes[i] - ep) if pos == "long" else (ep - closes[i])
            if unr >= partial_tp:
                tpls.append(unr)
                partial_taken = True

        # 2) Add to winners
        if add_start > 0 and pos != "flat" and ep is not None:
            profit = (closes[i] - ep) if pos == "long" else (ep - closes[i])
            if profit > 0 and next_add_lvl > 0 and profit >= next_add_lvl:
                while profit >= next_add_lvl:
                    added.append(closes[i])
                    total_adds += 1
                    cur_c = (1 if partial_taken else 2) + len(added)
                    if cur_c > max_c: max_c = cur_c
                    next_add_lvl += add_interval

        # 3) Signal
        if si < len(filtered) and times[i] == filtered[si][0]:
            ts, sig, price = filtered[si]; si += 1
            shielded = False
            if _WM_SHIELD > 0 and pos != "flat" and i >= _WM_LB:
                ws = max(0, i - _WM_LB)
                if pos == "long" and sig == "SELL":
                    for lvl, _ in find_clusters(lows[ws:i], times[ws:i]):
                        if lvl < closes[i] and (closes[i] - lvl) <= _WM_SHIELD:
                            shielded = True; break
                elif pos == "short" and sig == "BUY":
                    for lvl, _ in find_clusters(highs[ws:i], times[ws:i]):
                        if lvl > closes[i] and (lvl - closes[i]) <= _WM_SHIELD:
                            shielded = True; break
            if not shielded:
                if pos != "flat" and ep is not None:
                    if (pos == "long" and sig == "SELL") or (pos == "short" and sig == "BUY"):
                        close_position(price)
                if sig == "BUY": pos, ep, eb = "long", price, i
                else: pos, ep, eb = "short", price, i
                partial_taken = False; added = []
                next_add_lvl = add_start if add_start > 0 else 0
            continue

        # 4) Spike exit
        if pos != "flat" and ep is not None and i > eb:
            if i - eb <= _SPIKE_BARS:
                mv = (closes[i] - ep) if pos == "long" else (ep - closes[i])
                if mv >= _SPIKE_PTS:
                    close_position(closes[i])

    if pos != "flat" and ep is not None:
        close_position(closes[-1])

    return {"total_pts": sum(tpls), "trades": len(tpls), "max_c": max_c,
            "total_adds": total_adds}


# ── Test combos: (partial_tp, add_start, add_interval, label) ────────────────
combos = [
    # Baseline
    (50,  0,   0,   "BASELINE (TP@50, no add)"),
    # A) Pure pyramid: no partial TP, add at intervals
    (0,   50,  50,  "A: no TP, add@50 every 50"),
    (0,   75,  75,  "A: no TP, add@75 every 75"),
    (0,   100, 100, "A: no TP, add@100 every 100"),
    # B) Layered: sell half at 50, then add starting at higher levels
    (50,  75,  50,  "B: TP@50, add@75 every 50"),
    (50,  100, 50,  "B: TP@50, add@100 every 50"),
    (50,  75,  75,  "B: TP@50, add@75 every 75"),
    (50,  100, 75,  "B: TP@50, add@100 every 75"),
    (50,  100, 100, "B: TP@50, add@100 every 100"),
    (50,  150, 100, "B: TP@50, add@150 every 100"),
]

hdr = (f"{'Label':<30} {'Total USD':>14} {'Pts/c/day':>10} {'MaxC':>5} "
       f"{'Adds':>6} {'Worst':>10} {'Best':>10}")
print(hdr)
print("-" * len(hdr))

for ptp, a_start, a_int, label in combos:
    agg_pts = 0.0; daily_pls = []; peak_c = 2; total_adds = 0
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
        r = run_bt(algo, ptp, a_start, a_int)
        if r:
            agg_pts += r["total_pts"]
            daily_pls.append(r["total_pts"])
            if r["max_c"] > peak_c: peak_c = r["max_c"]
            total_adds += r["total_adds"]

    n = len(daily_pls) if daily_pls else 1
    total_usd = agg_pts * _MUL
    avg_pts_cd = agg_pts / 2 / n
    worst = min(daily_pls) if daily_pls else 0
    best = max(daily_pls) if daily_pls else 0
    print(f"{label:<30} ${total_usd:>+12,.0f} {avg_pts_cd:>+9.1f} {peak_c:>5} "
          f"{total_adds:>6} {worst:>+9.0f} pts {best:>+9.0f} pts")

print(f"\nPts/c/day = total pts / 2 base contracts / {n} days")
print("Added contracts are extra exposure on top of the 2 base contracts.", flush=True)
