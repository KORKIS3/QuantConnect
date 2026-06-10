"""Compare Ray Engine vs Pinball Engine — full backtest on all available days.

Both engines use IDENTICAL:
- Data (same CSVs, same session window)
- Ray computation (same TradingAlgoFast output)
- Contract count (2 contracts)
- Partial TP (50 pts on 1 contract)

The ONLY difference is the buy/sell trigger logic:
- Ray Engine: fires on ray crossings (from _run_signals_nb in TradingAlgoFast.py)
- Pinball Engine: fires on its own CHOP/TREND logic (from belief_engine_pinball.py)

Usage: python _backtest_compare_engines.py [--quick] [--max-days N]
"""

import argparse, os, time, sys
import pandas as pd, pytz, numpy as np

from TradingAlgoFast import AlgoConfig, run_trading_algo_fast
from belief_engine_pinball import PinballEngine, PinballConfig

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
_CONTRACTS = 2
_MULTIPLIER = 5


def run_ray_engine(day_data, target_date, end_time, config):
    """Run the ray-crossing engine and return session P/L."""
    algo_df = run_trading_algo_fast(day_data, target_date, "09:30", end_time, config=config)
    end_ts = pd.Timestamp(f"{target_date} {end_time}", tz=_EST)
    sliced = algo_df[algo_df.index <= end_ts]
    if len(sliced) < 2:
        return 0.0, 0, algo_df
    pl = float(sliced["session_pl"].iloc[-1])
    trades = int(sliced["rolling_buy_count"].iloc[-1] + sliced["rolling_sell_count"].iloc[-1])
    return pl, trades, algo_df


def run_pinball_engine(algo_df, target_date, end_time):
    """Run Pinball on the SAME algo_df (same rays) and return session P/L."""
    end_ts = pd.Timestamp(f"{target_date} {end_time}", tz=_EST)
    sliced = algo_df[algo_df.index <= end_ts]
    if len(sliced) < 2:
        return 0.0, 0

    # Use the SAME config as live trading (session_end_time matches end_time)
    cfg = PinballConfig()
    cfg.session_end_time = end_time

    pinball = PinballEngine(cfg)
    pinball.run_session(sliced)

    pl = pinball.session_pl
    trades = pinball.trade_count
    return pl, trades


def main():
    parser = argparse.ArgumentParser(description="Compare Ray vs Pinball engines")
    parser.add_argument("--quick", action="store_true", help="Only run 9:30-10:30")
    parser.add_argument("--max-days", type=int, default=0, dest="max_days")
    args = parser.parse_args()

    end_time = "10:30" if args.quick else "17:00"

    # Ray engine config — same as Backtest2Year.py baseline
    ray_config = AlgoConfig(
        warmup_minutes=7,
        steep_angle_threshold=90.0,
        proximity_points=4.0,
        min_reversal_minutes=0,
        min_entry_angle=0.0,
        partial_tp_pts=50.0,
        wm_shield_distance=0.0,
        swing_anchor_threshold=10.0,
    )

    csv_files = sorted([f for f in os.listdir(_DATA_ROOT)
                        if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])
    if args.max_days > 0:
        csv_files = csv_files[-args.max_days:]

    total = len(csv_files)
    t_start = time.time()

    print(f"\n{'='*80}")
    print(f"  ENGINE COMPARISON BACKTEST")
    print(f"  Session: 09:30 - {end_time} ET")
    print(f"  Days: {total}")
    print(f"  Contracts: {_CONTRACTS}")
    print(f"  Ray Config: warmup=7, steep=90, prox=4, partial_tp=50, swing_anchor=10")
    print(f"  Pinball Config: session_end={end_time}, chop_tp=30, chop_stop=60, partial_tp=50")
    print(f"{'='*80}\n")

    ray_pls = []
    pin_pls = []
    ray_trades_total = 0
    pin_trades_total = 0
    days_processed = 0

    for i, fname in enumerate(csv_files):
        target_date = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
        fpath = os.path.join(_DATA_ROOT, fname)

        try:
            df = pd.read_csv(fpath, index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)

            day_start = pd.Timestamp(f"{target_date} 09:30", tz=_EST)
            day_end = pd.Timestamp(f"{target_date} {end_time}", tz=_EST)
            day_data = df[(df.index >= day_start) & (df.index <= day_end)]

            if len(day_data) < 15:
                continue
            if (day_data[["Open", "High", "Low", "Close"]] <= 0).any().any():
                continue
            if day_data["High"].max() == day_data["Low"].min():
                continue
            if day_data["Volume"].sum() < 100:
                continue

            # Run ray engine (also produces algo_df for Pinball)
            ray_pl, ray_trades, algo_df = run_ray_engine(day_data, target_date, end_time, ray_config)

            # Run Pinball on the SAME algo_df
            pin_pl, pin_trades = run_pinball_engine(algo_df, target_date, end_time)

            ray_pls.append(ray_pl)
            pin_pls.append(pin_pl)
            ray_trades_total += ray_trades
            pin_trades_total += pin_trades
            days_processed += 1

            if (i + 1) % 50 == 0:
                elapsed = time.time() - t_start
                print(f"  [{i+1}/{total}] {elapsed:.0f}s elapsed ...")

        except Exception as exc:
            continue

    elapsed = time.time() - t_start
    print(f"\nProcessed {days_processed} days in {elapsed:.1f}s\n")

    # Results
    ray_total = sum(ray_pls)
    pin_total = sum(pin_pls)
    ray_avg = np.mean(ray_pls) if ray_pls else 0
    pin_avg = np.mean(pin_pls) if pin_pls else 0
    ray_win_days = sum(1 for p in ray_pls if p > 0)
    pin_win_days = sum(1 for p in pin_pls if p > 0)
    ray_lose_days = sum(1 for p in ray_pls if p <= 0)
    pin_lose_days = sum(1 for p in pin_pls if p <= 0)
    ray_win_pct = ray_win_days / days_processed * 100 if days_processed else 0
    pin_win_pct = pin_win_days / days_processed * 100 if days_processed else 0

    print(f"{'='*80}")
    print(f"{'METRIC':<25} {'RAY ENGINE':>20} {'PINBALL ENGINE':>20}")
    print(f"{'='*80}")
    print(f"{'Total Points':<25} {ray_total:>+20,.0f} {pin_total:>+20,.0f}")
    print(f"{'Avg Pts/Day':<25} {ray_avg:>+20.1f} {pin_avg:>+20.1f}")
    print(f"{'Total Trades':<25} {ray_trades_total:>20,} {pin_trades_total:>20,}")
    print(f"{'Win Days':<25} {ray_win_days:>20} {pin_win_days:>20}")
    print(f"{'Lose Days':<25} {ray_lose_days:>20} {pin_lose_days:>20}")
    print(f"{'Win %':<25} {ray_win_pct:>19.1f}% {pin_win_pct:>19.1f}%")
    print(f"{'P/L (USD)':<25} ${ray_total*_MULTIPLIER:>18,.0f} ${pin_total*_MULTIPLIER:>18,.0f}")
    print(f"{'='*80}")

    # Difference
    diff = pin_total - ray_total
    print(f"\nPinball vs Ray: {diff:+,.0f} pts ({diff/days_processed:+.1f} pts/day)" if days_processed else "")
    if pin_avg > ray_avg:
        print(f"  → Pinball is BETTER by {pin_avg - ray_avg:.1f} pts/day")
    else:
        print(f"  → Ray is BETTER by {ray_avg - pin_avg:.1f} pts/day")

    # Worst/best days comparison
    if ray_pls and pin_pls:
        diffs = [p - r for r, p in zip(ray_pls, pin_pls)]
        print(f"\n  Pinball's best day vs Ray: {max(diffs):+.0f} pts")
        print(f"  Pinball's worst day vs Ray: {min(diffs):+.0f} pts")
        print(f"  Days Pinball beats Ray: {sum(1 for d in diffs if d > 0)}/{days_processed}")


if __name__ == "__main__":
    main()
