"""Trailing stop line test (Approach B — angled line from swing points).
Once a trade is profitable by activation_pts, draw a trailing line at trail_angle
from the most recent swing high (for shorts) or swing low (for longs).
While active, suppress normal ray-cross reversals. Only exit on close across the line.
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
print(f"Trailing stop line test on {len(csv_files)} days (day session 9:30-17:00)\n", flush=True)

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
    """Find the highest high in the last `lookback` bars ending at end_idx."""
    start = max(0, end_idx - lookback + 1)
    segment = highs[start:end_idx + 1]
    if len(segment) == 0: return None, None
    best_idx = start + int(np.argmax(segment))
    return float(highs[best_idx]), best_idx


def find_swing_low(lows, end_idx, lookback=5):
    """Find the lowest low in the last `lookback` bars ending at end_idx."""
    start = max(0, end_idx - lookback + 1)
    segment = lows[start:end_idx + 1]
    if len(segment) == 0: return None, None
    best_idx = start + int(np.argmin(segment))
    return float(lows[best_idx]), best_idx


def trail_line_value(anchor_price, anchor_bar, current_bar, angle_deg, direction):
    """Calculate the trailing line value at current_bar.
    direction='long': line goes UP from anchor (ascending support)
    direction='short': line goes DOWN from anchor (descending resistance)
    angle_deg is the magnitude (always positive).
    Returns the line price at current_bar.
    """
    bars_elapsed = current_bar - anchor_bar
    if bars_elapsed < 0: return anchor_price
    # Convert angle to pts/bar. At 60°, tan(60°) ≈ 1.73.
    # But we need to scale — on a 1-min chart, 60° visually is roughly 5-15 pts/bar
    # depending on the price scale. Let's use pts_per_bar directly instead of angle.
    # Actually, let's parameterize as pts_per_bar to keep it simple and testable.
    # We'll call it "slope" — pts the line moves per bar.
    # For now, angle_deg is actually pts_per_bar (we'll rename in the combos).
    pts_per_bar = angle_deg
    if direction == "long":
        return anchor_price + pts_per_bar * bars_elapsed  # line rises
    else:
        return anchor_price - pts_per_bar * bars_elapsed  # line falls


def run_bt(algo_df, activation_pts, trail_slope, swing_lookback, reanchor):
    """Replay with trailing stop line.
    activation_pts: unrealized profit to activate trailing line (0=disabled=baseline)
    trail_slope: pts/bar the trailing line moves (steeper = tighter)
    swing_lookback: bars to look back for swing high/low anchor
    reanchor: if True, re-anchor to new swing points as trade progresses
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

    si = 0; tpls = []; pos = "flat"; ep = None; eb = 0
    partial_taken = False
    # Trailing line state
    trail_active = False
    trail_anchor_price = None
    trail_anchor_bar = None
    trail_exits = 0; suppressed_signals = 0

    def close_position(exit_price):
        nonlocal pos, ep, eb, partial_taken, trail_active, trail_anchor_price, trail_anchor_bar
        base_remaining = 1 if partial_taken else 2
        base_pl = (exit_price - ep) if pos == "long" else (ep - exit_price)
        for _ in range(base_remaining):
            tpls.append(base_pl)
        trail_active = False; trail_anchor_price = None; trail_anchor_bar = None
        pos, ep, eb = "flat", None, 0
        partial_taken = False

    for i in range(len(algo_df)):
        # 1) Partial take-profit
        if _PARTIAL_TP > 0 and pos != "flat" and ep is not None and not partial_taken:
            unr = (closes[i] - ep) if pos == "long" else (ep - closes[i])
            if unr >= _PARTIAL_TP:
                tpls.append(unr)
                partial_taken = True

        # 2) Activate trailing line once profit exceeds threshold
        if activation_pts > 0 and pos != "flat" and ep is not None and not trail_active:
            profit = (closes[i] - ep) if pos == "long" else (ep - closes[i])
            if profit >= activation_pts:
                # Anchor at recent swing point
                if pos == "long":
                    anchor_p, anchor_b = find_swing_low(lows, i, swing_lookback)
                else:
                    anchor_p, anchor_b = find_swing_high(highs, i, swing_lookback)
                if anchor_p is not None:
                    trail_active = True
                    trail_anchor_price = anchor_p
                    trail_anchor_bar = anchor_b

        # 3) Re-anchor trailing line if enabled and a better swing point appears
        if trail_active and reanchor and pos != "flat":
            if pos == "long":
                new_p, new_b = find_swing_low(lows, i, swing_lookback)
                if new_p is not None and new_b > trail_anchor_bar:
                    # Only re-anchor if the new swing low is HIGHER (tighter for longs)
                    new_line_val = trail_line_value(new_p, new_b, i, trail_slope, "long")
                    old_line_val = trail_line_value(trail_anchor_price, trail_anchor_bar, i, trail_slope, "long")
                    if new_line_val > old_line_val:
                        trail_anchor_price = new_p
                        trail_anchor_bar = new_b
            else:
                new_p, new_b = find_swing_high(highs, i, swing_lookback)
                if new_p is not None and new_b > trail_anchor_bar:
                    # Only re-anchor if the new swing high is LOWER (tighter for shorts)
                    new_line_val = trail_line_value(new_p, new_b, i, trail_slope, "short")
                    old_line_val = trail_line_value(trail_anchor_price, trail_anchor_bar, i, trail_slope, "short")
                    if new_line_val < old_line_val:
                        trail_anchor_price = new_p
                        trail_anchor_bar = new_b

        # 4) Check trailing line exit (CLOSE across the line)
        if trail_active and pos != "flat" and trail_anchor_price is not None:
            line_val = trail_line_value(trail_anchor_price, trail_anchor_bar, i, trail_slope, pos)
            if pos == "long" and closes[i] < line_val:
                close_position(closes[i])
                trail_exits += 1
                continue
            elif pos == "short" and closes[i] > line_val:
                close_position(closes[i])
                trail_exits += 1
                continue

        # 5) Signal check — suppressed if trailing line is active
        if si < len(filtered) and times[i] == filtered[si][0]:
            ts, sig, price = filtered[si]; si += 1

            # If trailing line is active, suppress reversal signals
            if trail_active and pos != "flat":
                if (pos == "long" and sig == "SELL") or (pos == "short" and sig == "BUY"):
                    suppressed_signals += 1
                    continue  # skip this signal, trailing line governs exit

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
                partial_taken = False
                trail_active = False; trail_anchor_price = None; trail_anchor_bar = None
            continue

        # 6) Spike exit
        if pos != "flat" and ep is not None and i > eb:
            if i - eb <= _SPIKE_BARS:
                mv = (closes[i] - ep) if pos == "long" else (ep - closes[i])
                if mv >= _SPIKE_PTS:
                    close_position(closes[i])

    if pos != "flat" and ep is not None:
        close_position(closes[-1])

    return {"total_pts": sum(tpls), "trades": len(tpls),
            "trail_exits": trail_exits, "suppressed": suppressed_signals}


# ── Test combos: (activation_pts, trail_slope, swing_lookback, reanchor, label) ──
combos = [
    # Baseline
    (0,   0,  0, False, "BASELINE (no trail)"),
    # Vary activation threshold (when to start trailing)
    (30,  3,  5, True,  "Act@30 slope=3 lb=5"),
    (50,  3,  5, True,  "Act@50 slope=3 lb=5"),
    (75,  3,  5, True,  "Act@75 slope=3 lb=5"),
    # Vary slope (pts/bar — steeper = tighter stop)
    (50,  1,  5, True,  "Act@50 slope=1 lb=5"),
    (50,  2,  5, True,  "Act@50 slope=2 lb=5"),
    (50,  5,  5, True,  "Act@50 slope=5 lb=5"),
    (50,  8,  5, True,  "Act@50 slope=8 lb=5"),
    # Vary lookback for swing anchor
    (50,  3,  3, True,  "Act@50 slope=3 lb=3"),
    (50,  3, 10, True,  "Act@50 slope=3 lb=10"),
    # No re-anchor (fixed anchor from activation point)
    (50,  3,  5, False, "Act@50 slope=3 lb=5 noRA"),
]

hdr = (f"{'Label':<28} {'Total USD':>14} {'Pts/c/day':>10} "
       f"{'TrailEx':>8} {'Suppressed':>11} {'Worst':>10} {'Best':>10}")
print(hdr)
print("-" * len(hdr))

for act, slope, lb, ra, label in combos:
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
        r = run_bt(algo, act, slope, lb, ra)
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
    print(f"{label:<28} ${total_usd:>+12,.0f} {avg_pts_cd:>+9.1f} "
          f"{t_exits:>8} {t_supp:>11} {worst:>+9.0f} pts {best:>+9.0f} pts")

print(f"\nPts/c/day = total pts / 2 base contracts / {n} days")
print("TrailEx = trades exited by trailing line. Suppressed = ray-cross signals ignored while trailing.")
print("Slope = pts/bar the trailing line moves. lb = bars lookback for swing anchor.", flush=True)
