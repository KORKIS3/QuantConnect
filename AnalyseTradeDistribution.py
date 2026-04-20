"""AnalyseTradeDistribution.py

Analyses the distribution of winning and losing trades across all 535 days
using the current proven settings (warmup=12, min_reversal=10).

Also tests hard stop-loss cutoffs to find the optimal max loss per trade.
"""

import os
import pandas as pd
import pytz
import numpy as np
from TradingAlgoFast import run_trading_algo_fast as run_trading_algo, AlgoConfig
from Backtest2Year import calc_pl

_EST       = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1000")
_CONTRACTS = 2
_MULTIPLIER = 5


def get_all_trades() -> list:
    """Return all individual trade P/L values."""
    csv_files = sorted([
        f for f in os.listdir(_DATA_ROOT)
        if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")
    ])
    config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0,
                        proximity_points=15.0, min_reversal_minutes=0)
    all_trades = []

    for fname in csv_files:
        target_date = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
        fpath = os.path.join(_DATA_ROOT, fname)
        try:
            df = pd.read_csv(fpath, index_col=0, parse_dates=True)
            df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
            if len(df) < 10:
                continue
            algo_df = run_trading_algo(df, target_date, "09:30", "10:30", config=config)
        except Exception:
            continue

        trade_pls = calc_pl(algo_df, float(algo_df["Close"].iloc[-1]), min_minutes=10)
        all_trades.extend(trade_pls)

    return all_trades


def analyse(trades: list) -> None:
    winners = sorted([p for p in trades if p > 0], reverse=True)
    losers  = sorted([p for p in trades if p <= 0])

    print(f"\nTotal trades: {len(trades)}")
    print(f"Winners: {len(winners)}  Losers: {len(losers)}  Win%: {len(winners)/len(trades)*100:.1f}%")
    print(f"Total P/L: {sum(trades):+.0f} pts  ${sum(trades)*_CONTRACTS*_MULTIPLIER:+,.0f}")
    print(f"Avg winner: {np.mean(winners):+.1f} pts   Avg loser: {np.mean(losers):+.1f} pts")
    print(f"Best win:   {max(winners):.0f} pts   Worst loss: {min(losers):.0f} pts")

    print(f"\n--- TOP 20 WINNERS ---")
    for i, p in enumerate(winners[:20]):
        print(f"  #{i+1:2d}: +{p:.0f} pts  ${p*_CONTRACTS*_MULTIPLIER:+,.0f}")

    print(f"\n--- TOP 20 LOSERS ---")
    for i, p in enumerate(losers[:20]):
        print(f"  #{i+1:2d}: {p:.0f} pts  ${p*_CONTRACTS*_MULTIPLIER:+,.0f}")

    print(f"\n--- LOSS DISTRIBUTION ---")
    buckets = [(0,-25),(-25,-50),(-50,-75),(-75,-100),(-100,-150),(-150,-200),(-200,-999)]
    for hi, lo in buckets:
        count = sum(1 for p in losers if lo <= p < hi)
        total = sum(p for p in losers if lo <= p < hi)
        pct   = count / len(losers) * 100
        print(f"  {lo:>5} to {hi:>4}: {count:>4} trades ({pct:>5.1f}%)  total: {total:>8.0f} pts")

    print(f"\n--- STOP LOSS TEST (cap each loss at X pts) ---")
    print(f"  {'Stop':>6}  {'Total Pts':>10}  {'P/L USD':>12}  {'Improvement':>12}")
    baseline = sum(trades)
    for stop in [200, 175, 150, 125, 100, 75, 50]:
        capped = [max(p, -stop) for p in trades]
        total  = sum(capped)
        improvement = total - baseline
        print(f"  {stop:>6}  {total:>10.0f}  ${total*_CONTRACTS*_MULTIPLIER:>11,.0f}  {improvement:>+12.0f} pts")


if __name__ == "__main__":
    print("Loading all trades (warmup=12, rev=10)...")
    trades = get_all_trades()
    analyse(trades)
