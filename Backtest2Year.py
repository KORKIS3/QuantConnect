"""Backtest2Year.py — Two-session backtesting with proven strategy.
Strategy: min_reversal_minutes=0 in algo, post-hoc 10-min reversal filter,
          spike profit take (exit if unrealized >= 100 pts within 5 bars of entry).
Day session: 9:30-17:00 (fresh start each day)
Overnight session: 18:00-09:00 (fresh start each night)
"""

import argparse, os, time
import pandas as pd, pytz, numpy as np
from datetime import date, timedelta
from TradingAlgoFast import AlgoConfig
from TradingAlgoFast import run_trading_algo_fast

_EST        = pytz.timezone("US/Eastern")
_DATA_ROOT  = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
_CONTRACTS  = 2
_MULTIPLIER = 5

DAY_END_TIMES   = ["10:00","10:30","11:00","11:30","12:00","13:00","14:00","15:00","16:00","17:00"]
NIGHT_END_TIMES = ["03:30","04:00","05:00","06:00","07:00","08:00","09:00"]


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


def _calc_pl_from_engine(algo_df, start_ts, end_ts):
    """Read 2-contract P/L directly from the engine's session_pl column — single source of truth."""
    sliced = algo_df[(algo_df.index >= start_ts) & (algo_df.index <= end_ts)]
    if len(sliced) < 2:
        return None
    pl = float(sliced["session_pl"].iloc[-1])
    return [pl] if pl != 0.0 else None


def _process_day(fname, quick=False, steep_line_proximity=5.0, steep_line_exit_only=False):
    """Process a single day — runs in a worker process."""
    target_date = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
    fpath = os.path.join(_DATA_ROOT, fname)
    # Identical config to live IBDataBridge — single source of truth
    config = AlgoConfig(
        warmup_minutes=8,
        steep_angle_threshold=65.0,
        proximity_points=8.0,
        min_reversal_minutes=0,
        min_entry_angle=15.0,
        partial_tp_pts=50.0,
        spike_profit_pts=50.0,
        spike_profit_bars=9,
        wm_shield_distance=0.0,
        steep_line_reentry=False,
        steep_line_proximity=steep_line_proximity,  # USE THE PARAMETER
        steep_line_exit_only=steep_line_exit_only,  # USE THE PARAMETER
    )
    all_end_times = DAY_END_TIMES + ([] if quick else NIGHT_END_TIMES)
    result = {et: None for et in all_end_times}
    try:
        df = pd.read_csv(fpath, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        if len(df) < 10:
            return target_date, result

        day_start = pd.Timestamp(f"{target_date} 09:30", tz=_EST)
        day_end   = pd.Timestamp(f"{target_date} 10:30", tz=_EST) if quick else pd.Timestamp(f"{target_date} 16:59", tz=_EST)
        day_data  = df[(df.index >= day_start) & (df.index <= day_end)]
        end_str   = "10:30" if quick else "17:00"
        end_times = ["10:30"] if quick else DAY_END_TIMES
        # Guard: skip days with zero or negative prices (causes Numba heap corruption)
        if (day_data[["Open","High","Low","Close"]] <= 0).any().any():
            return target_date, result
        # Guard: skip days with no price movement (flat data = bad download)
        if day_data["High"].max() == day_data["Low"].min():
            return target_date, result
        # Guard: skip days with near-zero volume (garbage data causes Numba crash)
        if day_data["Volume"].sum() < 100:
            return target_date, result
        if len(day_data) >= 15:
            try:
                day_algo = run_trading_algo_fast(day_data, target_date, "09:30", end_str, config=config)
                for et in end_times:
                    end_ts = pd.Timestamp(f"{target_date} {et}", tz=_EST)
                    tpls = _calc_pl_from_engine(day_algo, day_start, end_ts)
                    if tpls:
                        result[et] = tpls
            except Exception:
                pass
    except Exception:
        pass
    return target_date, result


def run_backtest(max_days=0, quick=False, steep_line_proximity=5.0, steep_line_exit_only=False):
    csv_files = sorted([f for f in os.listdir(_DATA_ROOT)
                        if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])
    if max_days > 0: csv_files = csv_files[-max_days:]
    total = len(csv_files)
    t_start = time.time()
    mode = "quick 9:30-10:30 only" if quick else "full day 9:30-17:00"
    
    print(f"\n{'='*80}")
    print(f"CONFIG: steep_line_exit_only = {steep_line_exit_only}")
    print(f"{'='*80}\n")
    
    print(f"\nRunning backtest on {total} days ({mode}) ...\n")

    all_end_times = DAY_END_TIMES
    totals = {et: {"trades":0,"pl":0.0,"winners":0,"losers":0,"daily_pls":[],"session":""}
              for et in all_end_times}
    for et in DAY_END_TIMES:
        if et in totals: totals[et]["session"] = "DAY"
    for et in NIGHT_END_TIMES:
        if et in totals: totals[et]["session"] = "NIGHT"

    done = 0
    for fname in csv_files:
        done += 1
        print(f"  [{done}/{total}] {int(done/total*100)}%", end="\r")
        try:
            _, result = _process_day(fname, quick, steep_line_proximity, steep_line_exit_only)
        except Exception:
            continue
        for et, tpls in result.items():
            if tpls:
                day_pl = sum(tpls)
                totals[et]["trades"]    += 1   # 1 day = 1 result
                totals[et]["pl"]        += day_pl
                totals[et]["winners"]   += 1 if day_pl > 0 else 0
                totals[et]["losers"]    += 1 if day_pl <= 0 else 0
                totals[et]["daily_pls"].append(day_pl)

    print(f"\nDays processed: {done}  ({time.time()-t_start:.1f}s)")
    print(f"Contracts:      {_CONTRACTS} x ${_MULTIPLIER}/pt")
    print(f"Strategy:       engine handles all logic (spike exit, WM shield, partial TP, trailing stop v4)\n")

    print("=== DAY SESSION (9:30-17:00, 2c partial TP @50pts) ===")
    print(f"{'End Time':<12} {'Days':>7} {'Win':>8} {'Lose':>7} {'Win%':>6} {'Pts':>10} {'P/L USD':>12} {'Avg/Day':>8}")
    print("-" * 80)
    for et in DAY_END_TIMES:
        t = totals[et]
        tr = t["trades"]; wr = t["winners"]/tr*100 if tr else 0
        usd = t["pl"]*_MULTIPLIER; avg = np.mean(t["daily_pls"]) if t["daily_pls"] else 0
        print(f"{et:<12} {tr:>7} {t['winners']:>8} {t['losers']:>7} {wr:>5.1f}% {t['pl']:>10.0f} ${usd:>11,.0f} {avg:>+7.1f}")
    print()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=4001)
    p.add_argument("--skip-download", action="store_true", dest="skip_download")
    p.add_argument("--max-days", type=int, default=0, dest="max_days")
    p.add_argument("--quick", action="store_true", help="Only run 9:30-10:30 day session (fast mode)")
    p.add_argument("--steep-line-proximity", type=float, default=0.0, dest="steep_line_proximity", help="Suppress steep line reversal if within N pts of original ray")
    p.add_argument("--steep-line-exit-only", action="store_true", dest="steep_line_exit_only", help="Steep line cross exits to flat instead of reversing")
    args = p.parse_args()
    if not args.skip_download: download_all(args.port)
    run_backtest(max_days=args.max_days, quick=args.quick, steep_line_proximity=args.steep_line_proximity, steep_line_exit_only=args.steep_line_exit_only)
