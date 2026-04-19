"""Cost averaging test: add 1 contract every X pts of drawdown on losing trades.
Day session only (9:30-17:00), 2-year backtest.
Base: 2 contracts, sell half at 50pts.
Option: bail_at_even=True exits the ENTIRE position (base + added) once total unrealized >= 0.
All P/L in points, converted to USD at the end."""
import os, sys
import pandas as pd, pytz, numpy as np
from TradingAlgo import AlgoConfig
from TradingAlgoFast import run_trading_algo_fast

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0, max_loss_per_trade=0)
csv_files = sorted([f for f in os.listdir(_DATA_ROOT) if f.endswith(".csv")])
print(f"Cost averaging test on {len(csv_files)} days (day session 9:30-17:00)\n", flush=True)

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


def run_bt(algo_df, avg_interval, bail_at_even=False):
    """Replay day session with optional cost averaging + bail-at-even.
    Returns dict with total_pts, trade_count, max_contracts, avg_adds_per_trade, bail_count."""
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
    tpls = []          # each entry = pts for 1 contract-equivalent
    pos = "flat"; ep = None; eb = 0
    partial_taken = False

    # Cost avg state
    added = []         # list of entry prices for added contracts (1 each)
    max_c = 2; next_lvl = 0
    total_adds = 0; total_trades = 0; bail_count = 0

    def calc_total_unrealized(price):
        """Total unrealized P/L in pts across ALL contracts (base + added)."""
        if pos == "flat" or ep is None: return 0
        base_remaining = 1 if partial_taken else 2
        base_unr = ((price - ep) if pos == "long" else (ep - price)) * base_remaining
        add_unr = 0
        for ap in added:
            add_unr += (price - ap) if pos == "long" else (ap - price)
        return base_unr + add_unr

    def close_position(exit_price, reason="signal"):
        """Close everything. Append pts per contract-equivalent to tpls."""
        nonlocal pos, ep, eb, partial_taken, added, next_lvl, bail_count
        # Base remaining
        base_remaining = 1 if partial_taken else 2
        base_pl = (exit_price - ep) if pos == "long" else (ep - exit_price)
        for _ in range(base_remaining):
            tpls.append(base_pl)
        # Added contracts
        for ap in added:
            apl = (exit_price - ap) if pos == "long" else (ap - exit_price)
            tpls.append(apl)
        if reason == "bail": bail_count += 1
        added = []; next_lvl = 0
        pos, ep, eb = "flat", None, 0
        partial_taken = False

    for i in range(len(algo_df)):
        # 1) Partial take-profit on base (half at 50pts)
        if pos != "flat" and ep is not None and not partial_taken:
            unr = (closes[i] - ep) if pos == "long" else (ep - closes[i])
            if unr >= _PARTIAL_TP:
                tpls.append(unr)  # 1 contract's pts
                partial_taken = True

        # 2) Cost averaging: add 1 contract at each drawdown interval
        if avg_interval > 0 and pos != "flat" and ep is not None:
            dd = (ep - closes[i]) if pos == "long" else (closes[i] - ep)
            if dd > 0 and next_lvl > 0 and dd >= next_lvl:
                while dd >= next_lvl:
                    added.append(closes[i])
                    total_adds += 1
                    cur_c = (1 if partial_taken else 2) + len(added)
                    if cur_c > max_c: max_c = cur_c
                    next_lvl += avg_interval

        # 3) Bail at even: if we have added contracts and total unrealized >= 0, exit flat
        if bail_at_even and len(added) > 0 and pos != "flat" and ep is not None:
            total_unr = calc_total_unrealized(closes[i])
            if total_unr >= 0:
                close_position(closes[i], reason="bail")
                continue

        # 4) Signal check
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
                        close_position(price, reason="signal")
                        total_trades += 1
                # Open new
                if sig == "BUY": pos, ep, eb = "long", price, i
                else: pos, ep, eb = "short", price, i
                partial_taken = False; added = []
                next_lvl = avg_interval if avg_interval > 0 else 0
                total_trades += 1
            continue

        # 5) Spike exit
        if pos != "flat" and ep is not None and i > eb:
            if i - eb <= _SPIKE_BARS:
                mv = (closes[i] - ep) if pos == "long" else (ep - closes[i])
                if mv >= _SPIKE_PTS:
                    close_position(closes[i], reason="spike")
                    total_trades += 1

    # Session end close
    if pos != "flat" and ep is not None:
        close_position(closes[-1], reason="eod")
        total_trades += 1

    total_pts = sum(tpls)
    return {
        "total_pts": total_pts,
        "trades": len(tpls),
        "max_c": max_c,
        "total_adds": total_adds,
        "total_trades": total_trades,
        "bail_count": bail_count,
    }


# ── Test combos ──────────────────────────────────────────────────────────────
combos = [
    (0,   False, "BASELINE (no avg)"),
    (100, False, "Avg@100 (no bail)"),
    (200, False, "Avg@200 (no bail)"),
    (100, True,  "Avg@100 + bail@even"),
    (200, True,  "Avg@200 + bail@even"),
]

hdr = (f"{'Label':<24} {'Total USD':>14} {'Pts/c/day':>10} {'MaxC':>5} "
       f"{'Adds':>6} {'Bails':>6} {'Worst':>10} {'Best':>10}")
print(hdr)
print("-" * len(hdr))

for interval, bail, label in combos:
    agg_pts = 0.0; daily_pls = []; peak_c = 2; total_adds = 0; total_bails = 0
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
        r = run_bt(algo, interval, bail_at_even=bail)
        if r:
            agg_pts += r["total_pts"]
            daily_pls.append(r["total_pts"])
            if r["max_c"] > peak_c: peak_c = r["max_c"]
            total_adds += r["total_adds"]
            total_bails += r["bail_count"]

    n = len(daily_pls) if daily_pls else 1
    total_usd = agg_pts * _MUL
    # pts per contract per day: divide by 2 base contracts (added contracts are bonus/risk)
    avg_pts_cd = agg_pts / 2 / n
    worst = min(daily_pls) if daily_pls else 0
    best = max(daily_pls) if daily_pls else 0
    print(f"{label:<24} ${total_usd:>+12,.0f} {avg_pts_cd:>+9.1f} {peak_c:>5} "
          f"{total_adds:>6} {total_bails:>6} {worst:>+9.0f} pts {best:>+9.0f} pts")

print(f"\nPts/c/day = total pts / 2 base contracts / {len(daily_pls) if daily_pls else 'N'} days")
print("MaxC = peak contracts held at once. Adds = total added contracts across all days.")
print("Bails = trades exited at breakeven (bail@even). Worst/Best = single day pts (all contracts).", flush=True)
