"""Backtest2Year.py — Fast backtesting with end-time sweep."""

import argparse, os, time
import pandas as pd, pytz, numpy as np
from datetime import date, timedelta
from TradingAlgo import AlgoConfig
from TradingAlgoFast import run_trading_algo_fast

_EST        = pytz.timezone("US/Eastern")
_DATA_ROOT  = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
_CONTRACTS  = 2
_MULTIPLIER = 5
END_TIMES   = [
    "10:00", "10:30", "11:00", "11:30", "12:00",
    "13:00", "14:00", "15:00", "16:00",
    "17:00", "18:00", "19:00", "20:00", "21:00", "22:00", "23:00",
    "00:00", "01:00", "02:00", "03:00", "04:00", "05:00", "06:00",
    "07:00", "08:00", "09:00", "09:30",
]


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


def run_backtest(max_days=0):
    csv_files = sorted([f for f in os.listdir(_DATA_ROOT)
                        if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])
    if max_days > 0: csv_files = csv_files[-max_days:]
    print(f"\nRunning backtest on {len(csv_files)} days ...\n")

    config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                        proximity_points=15.0, min_reversal_minutes=10, max_loss_per_trade=0)

    totals = {et: {"trades":0,"pl":0.0,"winners":0,"losers":0,"daily_pls":[]} for et in END_TIMES}
    days_done = 0

    for fname in csv_files:
        target_date = fname.replace("CBOT_MINI_YM1_","").replace(".csv","")
        if target_date.startswith("2025-04"): days_done += 1; continue
        fpath = os.path.join(_DATA_ROOT, fname)
        try:
            df = pd.read_csv(fpath, index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
            if len(df) < 10: days_done += 1; continue
        except: days_done += 1; continue

        # Run fast algo ONCE on full day data (all 23 hours)
        try:
            algo_df = run_trading_algo_fast(df, target_date, "09:30", "09:29", config=config)
        except: days_done += 1; continue

        # Slice by end times and calc P/L with 10-min reversal filter
        # For end times after midnight (00:00-09:30), we need next-day timestamps
        for et in END_TIMES:
            try:
                end_ts = pd.Timestamp(f"{target_date} {et}", tz=_EST)
                sliced = algo_df[algo_df.index <= end_ts]
                if len(sliced) < 10: continue
                rows = sliced[sliced["signal"].isin(["BUY","SELL"])]
                if rows.empty: continue
                filtered = []
                for ts, row in rows.iterrows():
                    sig = row["signal"]
                    price = float(row["buy_price"] if sig=="BUY" else row["sell_price"])
                    filtered.append((ts, sig, price))
                last_close = float(sliced["Close"].iloc[-1])
                tpls = []; pos, ep = "flat", None
                for ts, sig, price in filtered:
                    if sig == "BUY":
                        if pos == "short" and ep: tpls.append(ep - price)
                        pos, ep = "long", price
                    elif sig == "SELL":
                        if pos == "long" and ep: tpls.append(price - ep)
                        pos, ep = "short", price
                if pos != "flat" and ep:
                    tpls.append((last_close - ep) if pos == "long" else (ep - last_close))
                if tpls:
                    day_pl = sum(tpls)
                    totals[et]["trades"] += len(tpls)
                    totals[et]["pl"] += day_pl
                    totals[et]["winners"] += sum(1 for p in tpls if p > 0)
                    totals[et]["losers"] += sum(1 for p in tpls if p <= 0)
                    totals[et]["daily_pls"].append(day_pl)
            except: continue

        days_done += 1
        print(f"  [{days_done}/{len(csv_files)}] {int(days_done/len(csv_files)*100)}%", end="\r")

    print(f"\nDays processed: {days_done}")
    print(f"Contracts:      {_CONTRACTS} x ${_MULTIPLIER}/pt\n")
    print(f"{'End Time':<12} {'Trades':>7} {'Win':>8} {'Lose':>7} {'Win%':>6} {'Pts':>10} {'P/L USD':>12} {'Avg/Day':>8}")
    print("-" * 80)
    for et in END_TIMES:
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
