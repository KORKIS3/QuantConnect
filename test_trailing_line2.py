"""Trailing stop line v2 — only suppress reversals while trade is still profitable.
If unrealized goes negative, let normal signals through again.
Also test: suppress only if trailing line hasn't been touched yet (line still ahead of price)."""
import os
import pandas as pd, pytz, numpy as np
from TradingAlgo import AlgoConfig
from TradingAlgoFast import run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0, max_loss_per_trade=0)
csv_files = sorted([f for f in os.listdir(_DATA_ROOT) if f.endswith(".csv")])
print(f"Trailing stop line v2 on {len(csv_files)} days (day session 9:30-17:00)\n", flush=True)

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


def find_swing_high(highs, end_idx, lookback=5):
    start = max(0, end_idx - lookback + 1)
    segment = highs[start:end_idx + 1]
    if len(segment) == 0: return None, None
    best_idx = start + int(np.argmax(segment))
    return float(highs[best_idx]), best_idx


def find_swing_low(lows, end_idx, lookback=5):
    start = max(0, end_idx - lookback + 1)
    segment = lows[start:end_idx + 1]
    if len(segment) == 0: return None, None
    best_idx = start + int(np.argmin(segment))
    return float(lows[best_idx]), best_idx


def run_bt(algo_df, activation_pts, trail_slope, swing_lookback, min_profit_to_suppress):
    """Replay with trailing stop line v2.
    min_profit_to_suppress: only suppress ray-cross reversals if current unrealized
    profit is >= this value. If profit drops below, let signals through normally.
    0 = always suppress once activated (v1 behavior).
    """
    rows = algo_df[algo_df["signal"].isin(["BUY", "SELL"])]
    if rows.empty: return None

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

    si = 0; tpls = []; pos = "flat"; ep = None; eb = 0
    partial_taken = False
    trail_active = False; t_anchor_p = None; t_anchor_b = None
    trail_exits = 0; suppressed = 0

    def close_pos(exit_price):
        nonlocal pos, ep, eb, partial_taken, trail_active, t_anchor_p, t_anchor_b
        rem = 1 if partial_taken else 2
        pl = (exit_price - ep) if pos == "long" else (ep - exit_price)
        for _ in range(rem): tpls.append(pl)
        trail_active = False; t_anchor_p = None; t_anchor_b = None
        pos, ep, eb = "flat", None, 0; partial_taken = False

    for i in range(len(algo_df)):
        # 1) Partial TP
        if _PARTIAL_TP > 0 and pos != "flat" and ep is not None and not partial_taken:
            unr = (closes[i] - ep) if pos == "long" else (ep - closes[i])
            if unr >= _PARTIAL_TP:
                tpls.append(unr); partial_taken = True

        # 2) Activate trailing line
        if activation_pts > 0 and pos != "flat" and ep is not None and not trail_active:
            profit = (closes[i] - ep) if pos == "long" else (ep - closes[i])
            if profit >= activation_pts:
                if pos == "long":
                    ap, ab = find_swing_low(lows, i, swing_lookback)
                else:
                    ap, ab = find_swing_high(highs, i, swing_lookback)
                if ap is not None:
                    trail_active = True; t_anchor_p = ap; t_anchor_b = ab

        # 3) Re-anchor trailing line
        if trail_active and pos != "flat":
            if pos == "long":
                np2, nb = find_swing_low(lows, i, swing_lookback)
                if np2 is not None and nb > t_anchor_b:
                    new_lv = t_anchor_p + trail_slope * (i - t_anchor_b)  # old line at bar i
                    # Only re-anchor if new anchor produces tighter (higher) line
                    new_line_from_new = np2 + trail_slope * (i - nb)
                    if new_line_from_new > new_lv:
                        t_anchor_p = np2; t_anchor_b = nb
            else:
                np2, nb = find_swing_high(highs, i, swing_lookback)
                if np2 is not None and nb > t_anchor_b:
                    new_lv = t_anchor_p - trail_slope * (i - t_anchor_b)
                    new_line_from_new = np2 - trail_slope * (i - nb)
                    if new_line_from_new < new_lv:
                        t_anchor_p = np2; t_anchor_b = nb

        # 4) Trailing line exit
        if trail_active and pos != "flat" and t_anchor_p is not None:
            if pos == "long":
                lv = t_anchor_p + trail_slope * (i - t_anchor_b)
                if closes[i] < lv:
                    close_pos(closes[i]); trail_exits += 1; continue
            else:
                lv = t_anchor_p - trail_slope * (i - t_anchor_b)
                if closes[i] > lv:
                    close_pos(closes[i]); trail_exits += 1; continue

        # 5) Signal — suppress if trailing active AND still profitable enough
        if si < len(filtered) and times[i] == filtered[si][0]:
            ts, sig, price = filtered[si]; si += 1

            if trail_active and pos != "flat":
                if (pos == "long" and sig == "SELL") or (pos == "short" and sig == "BUY"):
                    cur_profit = (closes[i] - ep) if pos == "long" else (ep - closes[i])
                    if cur_profit >= min_profit_to_suppress:
                        suppressed += 1; continue

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
                        close_pos(price)
                if sig == "BUY": pos, ep, eb = "long", price, i
                else: pos, ep, eb = "short", price, i
                partial_taken = False
                trail_active = False; t_anchor_p = None; t_anchor_b = None
            continue

        # 6) Spike exit
        if pos != "flat" and ep is not None and i > eb:
            if i - eb <= _SPIKE_BARS:
                mv = (closes[i] - ep) if pos == "long" else (ep - closes[i])
                if mv >= _SPIKE_PTS:
                    close_pos(closes[i])

    if pos != "flat" and ep is not None:
        close_pos(closes[-1])

    return {"total_pts": sum(tpls), "trades": len(tpls),
            "trail_exits": trail_exits, "suppressed": suppressed}


# ── Test combos ──────────────────────────────────────────────────────────────
# (activation_pts, trail_slope, swing_lookback, min_profit_to_suppress, label)
combos = [
    (0,   0,  0,  0,  "BASELINE (no trail)"),
    # v2: only suppress while profitable (min_profit >= 0)
    (50,  3,  5,  0,  "v2: Act@50 sl=3 suppress>=0"),
    (50,  5,  5,  0,  "v2: Act@50 sl=5 suppress>=0"),
    (50,  8,  5,  0,  "v2: Act@50 sl=8 suppress>=0"),
    # v2: only suppress while profit >= 20pts
    (50,  3,  5,  20, "v2: Act@50 sl=3 suppress>=20"),
    (50,  5,  5,  20, "v2: Act@50 sl=5 suppress>=20"),
    (50,  8,  5,  20, "v2: Act@50 sl=8 suppress>=20"),
    # v2: only suppress while profit >= 50pts (very conservative)
    (50,  3,  5,  50, "v2: Act@50 sl=3 suppress>=50"),
    (50,  5,  5,  50, "v2: Act@50 sl=5 suppress>=50"),
    # Higher activation
    (75,  5,  5,  0,  "v2: Act@75 sl=5 suppress>=0"),
    (75,  5,  5,  20, "v2: Act@75 sl=5 suppress>=20"),
    (100, 5,  5,  0,  "v2: Act@100 sl=5 suppress>=0"),
]

hdr = (f"{'Label':<32} {'Total USD':>14} {'Pts/c/day':>10} "
       f"{'TrailEx':>8} {'Supp':>6} {'Worst':>10} {'Best':>10}")
print(hdr)
print("-" * len(hdr))

for act, slope, lb, mps, label in combos:
    agg_pts = 0.0; daily_pls = []; t_exits = 0; t_supp = 0
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
        r = run_bt(algo, act, slope, lb, mps)
        if r:
            agg_pts += r["total_pts"]
            daily_pls.append(r["total_pts"])
            t_exits += r["trail_exits"]
            t_supp += r["suppressed"]

    n = len(daily_pls) if daily_pls else 1
    total_usd = agg_pts * _MUL
    avg_pts_cd = agg_pts / 2 / n
    worst = min(daily_pls) if daily_pls else 0
    best = max(daily_pls) if daily_pls else 0
    print(f"{label:<32} ${total_usd:>+12,.0f} {avg_pts_cd:>+9.1f} "
          f"{t_exits:>8} {t_supp:>6} {worst:>+9.0f} pts {best:>+9.0f} pts")

print(f"\nPts/c/day = total pts / 2 base contracts / {n} days", flush=True)
