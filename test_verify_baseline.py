"""Quick verify: compare cost_avg baseline to Backtest2Year for a few days."""
import os, sys
import pandas as pd, pytz, numpy as np
from TradingAlgo import AlgoConfig
from TradingAlgoFast import run_trading_algo_fast
sys.path.insert(0, ".")
import Backtest2Year as bt

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                    proximity_points=15.0, min_reversal_minutes=0, max_loss_per_trade=0)

_SPIKE_PTS, _SPIKE_BARS = 100, 5
_WM_SHIELD = 12.0; _WM_LB = 30; _WM_TOL = 12; _WM_MT = 4; _WM_MS = 15
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
            if abs(indexed[j][0] - base) <= _WM_TOL: group.append((indexed[j][0], indexed[j][1])); used.add(j)
            elif indexed[j][0] - base > _WM_TOL: break
        if len(group) >= _WM_MT:
            tt = sorted([g[1] for g in group])
            if (tt[-1]-tt[0]).total_seconds()/60 >= _WM_MS:
                clusters.append((float(np.mean([g[0] for g in group])), len(group)))
    return clusters

def run_baseline(algo_df):
    """Exact replica of Backtest2Year logic: 2 contracts, sell half at 50, return list of pts."""
    rows = algo_df[algo_df["signal"].isin(["BUY","SELL"])]
    if rows.empty: return None
    filtered = []
    for ts, row in rows.iterrows():
        sig = row["signal"]
        price = float(row["buy_price"] if sig == "BUY" else row["sell_price"])
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
        if pos != "flat" and ep is not None and not partial_taken:
            unr = (closes[i]-ep) if pos == "long" else (ep-closes[i])
            if unr >= _PARTIAL_TP:
                tpls.append(unr); partial_taken = True

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
                    tpls.append(price - ep)
                elif pos == "short" and sig == "BUY":
                    tpls.append(ep - price)
                if sig == "BUY": pos, ep, eb = "long", price, i
                else: pos, ep, eb = "short", price, i
                partial_taken = False
            continue

        if pos != "flat" and ep is not None and i > eb:
            if i - eb <= _SPIKE_BARS:
                mv = (closes[i]-ep) if pos == "long" else (ep-closes[i])
                if mv >= _SPIKE_PTS:
                    tpls.append(mv)
                    pos, ep, eb = "flat", None, 0; partial_taken = False

    if pos != "flat" and ep is not None:
        last_close = closes[-1]
        tpls.append((last_close-ep) if pos == "long" else (ep-last_close))
    return tpls

# Compare on 5 days
test_dates = ["2026-02-03","2026-02-04","2026-02-05","2026-02-09","2026-02-10"]
total_mine = 0; total_bt = 0
for dd in test_dates:
    fname = f"CBOT_MINI_YM1_{dd}.csv"
    fp = os.path.join(_DATA_ROOT, fname)
    if not os.path.exists(fp): print(f"  {dd}: file not found"); continue
    df = pd.read_csv(fp, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    ds = pd.Timestamp(f"{dd} 09:30", tz=_EST)
    de = pd.Timestamp(f"{dd} 17:00", tz=_EST)
    dd_data = df[(df.index >= ds) & (df.index <= de)]
    if len(dd_data) < 15: continue
    algo = run_trading_algo_fast(dd_data, dd, "09:30", "17:00", config=config)

    mine = run_baseline(algo)
    mine_pts = sum(mine) if mine else 0

    bt_tpls = bt._filter_and_calc_pl(algo, ds, de, partial_tp_pts=50)
    bt_pts = sum(bt_tpls) if bt_tpls else 0

    match = "OK" if abs(mine_pts - bt_pts) < 0.1 else "MISMATCH"
    print(f"{dd}: mine={mine_pts:+.1f}  bt={bt_pts:+.1f}  {match}")
    total_mine += mine_pts; total_bt += bt_pts

print(f"\nTotal: mine={total_mine:+.1f}  bt={total_bt:+.1f}")
