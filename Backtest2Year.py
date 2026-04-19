"""Backtest2Year.py — Two-session backtesting with proven strategy.
Strategy: min_reversal_minutes=0 in algo, post-hoc 10-min reversal filter,
          spike profit take (exit if unrealized >= 100 pts within 5 bars of entry).
Day session: 9:30-17:00 (fresh start each day)
Overnight session: 18:00-09:00 (fresh start each night)
"""

import argparse, os, time
import pandas as pd, pytz, numpy as np
from datetime import date, timedelta
from TradingAlgo import AlgoConfig
from TradingAlgoFast import run_trading_algo_fast

_EST        = pytz.timezone("US/Eastern")
_DATA_ROOT  = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
_CONTRACTS  = 2
_MULTIPLIER = 5

DAY_END_TIMES   = ["10:00","10:30","11:00","11:30","12:00","13:00","14:00","15:00","16:00","17:00"]
NIGHT_END_TIMES = ["19:00","20:00","21:00","22:00","23:00","00:00","01:00","02:00","03:00","04:00","05:00","06:00","07:00","08:00","09:00"]


def trading_days(start, end):
    d = start
    while d <= end:
        if d.weekday() < 5: yield d
        d += timedelta(days=1)


def download_all(port):
    from ib_insync import IB, Future
    ib = IB(); ib.connect("127.0.0.1", port, clientId=50, timeout=120)
    # Get all YM contracts including expired for front-month mapping
    base = Future(symbol="YM", exchange="CBOT", currency="USD", includeExpired=True)
    all_contracts = sorted([d.contract for d in ib.reqContractDetails(base)],
                           key=lambda c: c.lastTradeDateOrContractMonth)
    print(f"Found {len(all_contracts)} YM contracts")
    def front_month_for(d):
        d_str = d.strftime("%Y%m%d")
        for c in all_contracts:
            if c.lastTradeDateOrContractMonth >= d_str: return c
        return all_contracts[-1]
    os.makedirs(_DATA_ROOT, exist_ok=True)
    end_date = date.today(); start_date = end_date - timedelta(days=365*5+30)
    days = list(trading_days(start_date, end_date))
    print(f"Downloading {len(days)} days ...")
    for idx, d in enumerate(days):
        fname = os.path.join(_DATA_ROOT, f"CBOT_MINI_YM1_{d}.csv")
        if os.path.exists(fname): continue
        contract = front_month_for(d)
        end_utc = pd.Timestamp(f"{d} 17:00:00").tz_localize(_EST).astimezone(pytz.utc).strftime("%Y%m%d-%H:%M:%S")
        try:
            bars = ib.reqHistoricalData(contract, endDateTime=end_utc, durationStr="1 D",
                barSizeSetting="1 min", whatToShow="TRADES", useRTH=False, formatDate=1)
        except: continue
        if not bars: continue
        df = pd.DataFrame([{"time":b.date,"Open":b.open,"High":b.high,"Low":b.low,
                            "Close":b.close,"Volume":b.volume} for b in bars]).set_index("time")
        df.index = pd.to_datetime(df.index)
        df.index = df.index.tz_localize("UTC").tz_convert(_EST) if df.index.tz is None else df.index.tz_convert(_EST)
        if len(df) < 10: continue
        df.to_csv(fname); print(f"  [{idx+1}/{len(days)}] {d} ({contract.localSymbol}): {len(df)} bars"); time.sleep(0.5)
    ib.disconnect(); print("Download complete.")


def _find_wm_clusters(values, times, tolerance=12.0, min_touches=4, min_span=15.0):
    """Find price clusters for water mark shield."""
    if len(values) < min_touches:
        return []
    indexed = sorted(zip(values, times), key=lambda x: x[0])
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
            if abs(indexed[j][0] - base) <= tolerance:
                group.append((indexed[j][0], indexed[j][1]))
                used.add(j)
            elif indexed[j][0] - base > tolerance:
                break
        if len(group) >= min_touches:
            tt = sorted([g[1] for g in group])
            span = (tt[-1] - tt[0]).total_seconds() / 60
            if span >= min_span:
                clusters.append((float(np.mean([g[0] for g in group])), len(group)))
    return clusters


def _filter_and_calc_pl(algo_df, start_ts, end_ts, use_wm_shield=True, partial_tp_pts=0):
    """Slice, apply post-hoc 10-min reversal filter + spike profit take + water mark shield + partial TP.
    Spike rule: if unrealized profit >= 100 pts within 5 bars of entry, exit at that bar's close.
    Shield rule: suppress reversal if water mark cluster within 12 pts supports current position.
    Partial TP: sell half the position at partial_tp_pts profit, hold other half per system (0=disabled).
    """
    _SPIKE_PTS = 100
    _SPIKE_BARS = 5
    _WM_SHIELD = 12.0 if use_wm_shield else 0.0
    _WM_LOOKBACK = 30

    sliced = algo_df[(algo_df.index >= start_ts) & (algo_df.index <= end_ts)]
    if len(sliced) < 2: return None
    rows = sliced[sliced["signal"].isin(["BUY","SELL"])]
    if rows.empty: return None

    # Post-hoc 10-min reversal filter
    filtered = []
    for ts, row in rows.iterrows():
        sig = row["signal"]
        price = float(row["buy_price"] if sig == "BUY" else row["sell_price"])
        if not filtered:
            filtered.append((ts, sig, price)); continue
        last_ts, last_sig, _ = filtered[-1]
        if last_sig != sig:
            if (ts - last_ts).total_seconds() / 60 >= 10:
                filtered.append((ts, sig, price))
        else:
            filtered.append((ts, sig, price))

    if not filtered: return None

    # Bar-by-bar replay with spike profit take + water mark shield + partial TP
    closes = sliced["Close"].values.astype(float)
    highs = sliced["High"].values.astype(float)
    lows = sliced["Low"].values.astype(float)
    times = sliced.index
    sig_idx = 0
    tpls = []
    pos, ep, entry_bar = "flat", None, 0
    partial_taken = False  # has half the position been closed at partial_tp_pts?

    for i in range(len(sliced)):
        # Check partial take-profit
        if partial_tp_pts > 0 and pos != "flat" and ep is not None and not partial_taken:
            unrealized = (closes[i] - ep) if pos == "long" else (ep - closes[i])
            if unrealized >= partial_tp_pts:
                tpls.append(unrealized)  # half position closed at partial TP
                partial_taken = True

        # Check if this bar has a filtered signal
        if sig_idx < len(filtered) and times[i] == filtered[sig_idx][0]:
            ts, sig, price = filtered[sig_idx]; sig_idx += 1

            # Water mark shield: suppress reversals if cluster supports current position
            shielded = False
            if _WM_SHIELD > 0 and pos != "flat" and i >= _WM_LOOKBACK:
                ws = max(0, i - _WM_LOOKBACK)
                if pos == "long" and sig == "SELL":
                    for lvl, _ in _find_wm_clusters(lows[ws:i], times[ws:i]):
                        if lvl < closes[i] and (closes[i] - lvl) <= _WM_SHIELD:
                            shielded = True; break
                elif pos == "short" and sig == "BUY":
                    for lvl, _ in _find_wm_clusters(highs[ws:i], times[ws:i]):
                        if lvl > closes[i] and (lvl - closes[i]) <= _WM_SHIELD:
                            shielded = True; break

            if not shielded:
                if pos == "long" and sig == "SELL":
                    pl = price - ep
                    if partial_tp_pts > 0:
                        remaining = 1 if partial_taken else 2
                        for _ in range(remaining): tpls.append(pl)
                    else:
                        tpls.append(pl)  # all contracts (pts)
                elif pos == "short" and sig == "BUY":
                    pl = ep - price
                    if partial_tp_pts > 0:
                        remaining = 1 if partial_taken else 2
                        for _ in range(remaining): tpls.append(pl)
                    else:
                        tpls.append(pl)
                if sig == "BUY": pos, ep, entry_bar = "long", price, i
                else: pos, ep, entry_bar = "short", price, i
                partial_taken = False
            continue

        # Check spike exit: unrealized >= 100 pts within 5 bars of entry
        if pos != "flat" and ep is not None and i > entry_bar:
            bars_held = i - entry_bar
            if bars_held <= _SPIKE_BARS:
                move = (closes[i] - ep) if pos == "long" else (ep - closes[i])
                if move >= _SPIKE_PTS:
                    if partial_tp_pts > 0:
                        remaining = 1 if partial_taken else 2
                        for _ in range(remaining): tpls.append(move)
                    else:
                        tpls.append(move)
                    pos, ep, entry_bar = "flat", None, 0
                    partial_taken = False

    # Close any open position at slice end
    if pos != "flat" and ep is not None:
        last_close = closes[-1]
        pl = (last_close - ep) if pos == "long" else (ep - last_close)
        if partial_tp_pts > 0:
            remaining = 1 if partial_taken else 2
            for _ in range(remaining): tpls.append(pl)
        else:
            tpls.append(pl)

    return tpls if tpls else None


def run_backtest(max_days=0):
    csv_files = sorted([f for f in os.listdir(_DATA_ROOT)
                        if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])
    if max_days > 0: csv_files = csv_files[-max_days:]
    print(f"\nRunning backtest on {len(csv_files)} days ...\n")

    # PROVEN: min_reversal=0, post-hoc 10-min filter
    config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                        proximity_points=15.0, min_reversal_minutes=0, max_loss_per_trade=0)

    all_end_times = DAY_END_TIMES + NIGHT_END_TIMES
    totals = {et: {"trades":0,"pl":0.0,"winners":0,"losers":0,"daily_pls":[],"session":""}
              for et in all_end_times}
    for et in DAY_END_TIMES: totals[et]["session"] = "DAY"
    for et in NIGHT_END_TIMES: totals[et]["session"] = "NIGHT"
    days_done = 0

    for fname in csv_files:
        target_date = fname.replace("CBOT_MINI_YM1_","").replace(".csv","")
        fpath = os.path.join(_DATA_ROOT, fname)
        try:
            df = pd.read_csv(fpath, index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
            if len(df) < 10: days_done += 1; continue
        except: days_done += 1; continue

        # === DAY SESSION: 9:30-17:00 (fresh start) ===
        day_start = pd.Timestamp(f"{target_date} 09:30", tz=_EST)
        day_end   = pd.Timestamp(f"{target_date} 16:59", tz=_EST)
        day_data  = df[(df.index >= day_start) & (df.index <= day_end)]

        if len(day_data) >= 15:
            try:
                day_algo = run_trading_algo_fast(day_data, target_date, "09:30", "17:00", config=config)
                for et in DAY_END_TIMES:
                    end_ts = pd.Timestamp(f"{target_date} {et}", tz=_EST)
                    tpls = _filter_and_calc_pl(day_algo, day_start, end_ts, partial_tp_pts=50)
                    if tpls:
                        day_pl = sum(tpls)
                        totals[et]["trades"] += len(tpls)
                        totals[et]["pl"] += day_pl
                        totals[et]["winners"] += sum(1 for p in tpls if p > 0)
                        totals[et]["losers"] += sum(1 for p in tpls if p <= 0)
                        totals[et]["daily_pls"].append(day_pl)
            except: pass

        # === OVERNIGHT SESSION: 18:00 prev day - 09:00 this day (fresh start) ===
        night_start = pd.Timestamp(f"{target_date} 18:00", tz=_EST) - pd.Timedelta(days=1)
        night_end   = pd.Timestamp(f"{target_date} 09:00", tz=_EST)
        night_data  = df[(df.index >= night_start) & (df.index <= night_end)]

        if len(night_data) >= 15:
            try:
                night_algo = run_trading_algo_fast(night_data, target_date, "18:00", "09:00", config=config)
                for et in NIGHT_END_TIMES:
                    h = int(et.split(":")[0])
                    if h >= 18:
                        end_ts = pd.Timestamp(f"{target_date} {et}", tz=_EST) - pd.Timedelta(days=1)
                    else:
                        end_ts = pd.Timestamp(f"{target_date} {et}", tz=_EST)
                    tpls = _filter_and_calc_pl(night_algo, night_start, end_ts, use_wm_shield=False)
                    if tpls:
                        day_pl = sum(tpls)
                        totals[et]["trades"] += len(tpls)
                        totals[et]["pl"] += day_pl
                        totals[et]["winners"] += sum(1 for p in tpls if p > 0)
                        totals[et]["losers"] += sum(1 for p in tpls if p <= 0)
                        totals[et]["daily_pls"].append(day_pl)
            except: pass

        days_done += 1
        print(f"  [{days_done}/{len(csv_files)}] {int(days_done/len(csv_files)*100)}%", end="\r")

    print(f"\nDays processed: {days_done}")
    print(f"Contracts:      {_CONTRACTS} x ${_MULTIPLIER}/pt")
    print(f"Strategy:       min_rev=0 + post-hoc 10-min filter + spike exit (unreal>=100 in 5 bars) + wm shield 12pts\n")

    print("=== DAY SESSION (9:30 start, sell half @50pts) ===")
    print(f"{'End Time':<12} {'Trades':>7} {'Win':>8} {'Lose':>7} {'Win%':>6} {'Pts':>10} {'P/L USD':>12} {'Pts/Day':>8}")
    print("-" * 80)
    for et in DAY_END_TIMES:
        t = totals[et]
        tr = t["trades"]; wr = t["winners"]/tr*100 if tr else 0
        # With partial TP, each tpl entry is 1 contract's pts, so multiply by $5 only
        usd = t["pl"]*_MULTIPLIER
        # Avg pts/day per contract: total_usd / days / contracts / multiplier
        n_days = len(t["daily_pls"]) if t["daily_pls"] else 1
        avg_pts = t["pl"] / _CONTRACTS / n_days if n_days else 0
        print(f"{et:<12} {tr:>7} {t['winners']:>8} {t['losers']:>7} {wr:>5.1f}% {t['pl']:>10.0f} ${usd:>11,.0f} {avg_pts:>+7.1f}")

    print(f"\n=== OVERNIGHT SESSION (18:00 start, no partial TP) ===")
    print(f"{'End Time':<12} {'Trades':>7} {'Win':>8} {'Lose':>7} {'Win%':>6} {'Pts':>10} {'P/L USD':>12} {'Pts/Day':>8}")
    print("-" * 80)
    for et in NIGHT_END_TIMES:
        t = totals[et]
        tr = t["trades"]; wr = t["winners"]/tr*100 if tr else 0
        usd = t["pl"]*_CONTRACTS*_MULTIPLIER
        n_days = len(t["daily_pls"]) if t["daily_pls"] else 1
        avg_pts = t["pl"] / n_days if n_days else 0
        print(f"{et:<12} {tr:>7} {t['winners']:>8} {t['losers']:>7} {wr:>5.1f}% {t['pl']:>10.0f} ${usd:>11,.0f} {avg_pts:>+7.1f}")
    print()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=4001)
    p.add_argument("--skip-download", action="store_true", dest="skip_download")
    p.add_argument("--max-days", type=int, default=0, dest="max_days")
    args = p.parse_args()
    if not args.skip_download: download_all(args.port)
    run_backtest(max_days=args.max_days)
