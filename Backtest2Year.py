"""Backtest2Year.py — Two-session backtesting: Day (9:30-17:00) + Overnight (18:00-09:00)."""

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
    ib = IB(); ib.connect("127.0.0.1", port, clientId=20)
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
    end_date = date.today(); start_date = end_date - timedelta(days=365*2+30)
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
        df.to_csv(fname); print(f"  [{idx+1}/{len(days)}] {d}: {len(df)} bars"); time.sleep(0.5)
    ib.disconnect(); print("Download complete.")


def _calc_pl(algo_df, start_ts, end_ts):
    """Slice algo_df between start_ts and end_ts, compute trade P/L."""
    sliced = algo_df[(algo_df.index >= start_ts) & (algo_df.index <= end_ts)]
    if len(sliced) < 2: return None
    rows = sliced[sliced["signal"].isin(["BUY","SELL"])]
    if rows.empty: return None
    trades = [(ts, row["signal"], float(row["buy_price"] if row["signal"]=="BUY" else row["sell_price"]))
              for ts, row in rows.iterrows()]
    last_close = float(sliced["Close"].iloc[-1])
    tpls = []; pos, ep = "flat", None
    for ts, sig, price in trades:
        if sig == "BUY":
            if pos == "short" and ep: tpls.append(ep - price)
            pos, ep = "long", price
        elif sig == "SELL":
            if pos == "long" and ep: tpls.append(price - ep)
            pos, ep = "short", price
    if pos != "flat" and ep:
        tpls.append((last_close - ep) if pos == "long" else (ep - last_close))
    if not tpls: return None
    return tpls


def run_backtest(max_days=0):
    csv_files = sorted([f for f in os.listdir(_DATA_ROOT)
                        if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])
    if max_days > 0: csv_files = csv_files[-max_days:]
    print(f"\nRunning backtest on {len(csv_files)} days ...\n")

    config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                        proximity_points=15.0, min_reversal_minutes=10, max_loss_per_trade=0)

    all_end_times = DAY_END_TIMES + NIGHT_END_TIMES
    totals = {et: {"trades":0,"pl":0.0,"winners":0,"losers":0,"daily_pls":[],"session":""}
              for et in all_end_times}
    for et in DAY_END_TIMES: totals[et]["session"] = "DAY"
    for et in NIGHT_END_TIMES: totals[et]["session"] = "NIGHT"

    days_done = 0
    prev_date = None  # for overnight: need previous day's file

    for fidx, fname in enumerate(csv_files):
        target_date = fname.replace("CBOT_MINI_YM1_","").replace(".csv","")
        if target_date.startswith("2025-04"): days_done += 1; prev_date = target_date; continue
        fpath = os.path.join(_DATA_ROOT, fname)
        try:
            df = pd.read_csv(fpath, index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
            if len(df) < 10: days_done += 1; prev_date = target_date; continue
        except: days_done += 1; prev_date = target_date; continue

        # === SESSION 1: DAY (9:30 - 17:00) ===
        # Slice data from 9:30 onward, run algo fresh
        day_start = pd.Timestamp(f"{target_date} 09:30", tz=_EST)
        day_end   = pd.Timestamp(f"{target_date} 16:59", tz=_EST)
        day_data  = df[(df.index >= day_start) & (df.index <= day_end)]

        if len(day_data) >= 15:
            try:
                day_algo = run_trading_algo_fast(day_data, target_date, "09:30", "17:00", config=config)
                for et in DAY_END_TIMES:
                    end_ts = pd.Timestamp(f"{target_date} {et}", tz=_EST)
                    tpls = _calc_pl(day_algo, day_start, end_ts)
                    if tpls:
                        day_pl = sum(tpls)
                        totals[et]["trades"] += len(tpls)
                        totals[et]["pl"] += day_pl
                        totals[et]["winners"] += sum(1 for p in tpls if p > 0)
                        totals[et]["losers"] += sum(1 for p in tpls if p <= 0)
                        totals[et]["daily_pls"].append(day_pl)
            except: pass

        # === SESSION 2: OVERNIGHT (18:00 prev day - 09:00 this day) ===
        # The full_day CSV for target_date has data from ~18:00 (target_date - 1) to 16:59 (target_date)
        # Overnight = 18:00 on (target_date - 1) to 09:00 on target_date
        night_start = pd.Timestamp(f"{target_date} 18:00", tz=_EST) - pd.Timedelta(days=1)
        night_end   = pd.Timestamp(f"{target_date} 09:00", tz=_EST)
        night_data  = df[(df.index >= night_start) & (df.index <= night_end)]

        if len(night_data) >= 15:
            try:
                night_algo = run_trading_algo_fast(night_data, target_date, "18:00", "09:00", config=config)
                for et in NIGHT_END_TIMES:
                    h = int(et.split(":")[0])
                    # 19-23 are on the previous day, 00-09 are on target_date
                    if h >= 18:
                        end_ts = pd.Timestamp(f"{target_date} {et}", tz=_EST) - pd.Timedelta(days=1)
                    else:
                        end_ts = pd.Timestamp(f"{target_date} {et}", tz=_EST)
                    tpls = _calc_pl(night_algo, night_start, end_ts)
                    if tpls:
                        day_pl = sum(tpls)
                        totals[et]["trades"] += len(tpls)
                        totals[et]["pl"] += day_pl
                        totals[et]["winners"] += sum(1 for p in tpls if p > 0)
                        totals[et]["losers"] += sum(1 for p in tpls if p <= 0)
                        totals[et]["daily_pls"].append(day_pl)
            except: pass

        days_done += 1
        prev_date = target_date
        print(f"  [{days_done}/{len(csv_files)}] {int(days_done/len(csv_files)*100)}%", end="\r")

    # Print results
    print(f"\nDays processed: {days_done}")
    print(f"Contracts:      {_CONTRACTS} x ${_MULTIPLIER}/pt\n")

    print("=== DAY SESSION (9:30 start, fresh each day) ===")
    print(f"{'End Time':<12} {'Trades':>7} {'Win':>8} {'Lose':>7} {'Win%':>6} {'Pts':>10} {'P/L USD':>12} {'Avg/Day':>8}")
    print("-" * 80)
    for et in DAY_END_TIMES:
        t = totals[et]
        tr = t["trades"]; wr = t["winners"]/tr*100 if tr else 0
        usd = t["pl"]*_CONTRACTS*_MULTIPLIER; avg = np.mean(t["daily_pls"]) if t["daily_pls"] else 0
        print(f"{et:<12} {tr:>7} {t['winners']:>8} {t['losers']:>7} {wr:>5.1f}% {t['pl']:>10.0f} ${usd:>11,.0f} {avg:>+7.1f}")

    print(f"\n=== OVERNIGHT SESSION (18:00 start, fresh each night) ===")
    print(f"{'End Time':<12} {'Trades':>7} {'Win':>8} {'Lose':>7} {'Win%':>6} {'Pts':>10} {'P/L USD':>12} {'Avg/Day':>8}")
    print("-" * 80)
    for et in NIGHT_END_TIMES:
        t = totals[et]
        tr = t["trades"]; wr = t["winners"]/tr*100 if tr else 0
        usd = t["pl"]*_CONTRACTS*_MULTIPLIER; avg = np.mean(t["daily_pls"]) if t["daily_pls"] else 0
        print(f"{et:<12} {tr:>7} {t['winners']:>8} {t['losers']:>7} {wr:>5.1f}% {t['pl']:>10.0f} ${usd:>11,.0f} {avg:>+7.1f}")
    print()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=4001)
    p.add_argument("--skip-download", action="store_true", dest="skip_download")
    p.add_argument("--max-days", type=int, default=0, dest="max_days")
    args = p.parse_args()
    if not args.skip_download: download_all(args.port)
    run_backtest(max_days=args.max_days)
