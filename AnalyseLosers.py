"""AnalyseLosers.py

For each time filter (5-10 min), analyse the distribution of losing trades
and test stop-loss thresholds to find the optimal bail-out point.
"""

import os
import pandas as pd
import pytz
import numpy as np
from TradingAlgo import run_trading_algo, AlgoConfig
from Backtest2Year import run_variant, calc_pl

_EST        = pytz.timezone("US/Eastern")
_DATA_ROOT  = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "930_1000")
_CONTRACTS  = 100
_MULTIPLIER = 5


def get_all_trades(min_minutes: int) -> list:
    """Return list of all trade P/L values for a given time filter."""
    csv_files = sorted([
        f for f in os.listdir(_DATA_ROOT)
        if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")
    ])
    config = AlgoConfig(warmup_minutes=7, steep_angle_threshold=65.0, proximity_points=15.0)
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

        signals = algo_df[algo_df["signal"].isin(["BUY", "SELL"])].copy()
        if signals.empty:
            continue

        # Build filtered signal list.
        filtered = []
        for ts, row in signals.iterrows():
            sig   = row["signal"]
            price = float(row["buy_price"] if sig == "BUY" else row["sell_price"])
            if not filtered:
                filtered.append((ts, sig, price))
                continue
            last_ts, last_sig, last_price = filtered[-1]
            if last_sig != sig:
                mins_held = (ts - last_ts).total_seconds() / 60
                if mins_held >= min_minutes:
                    filtered.append((ts, sig, price))
            else:
                filtered.append((ts, sig, price))

        last_close = float(algo_df["Close"].iloc[-1])
        trade_pls  = calc_pl(filtered, last_close)
        all_trades.extend(trade_pls)

    return all_trades


def analyse_stop_loss(trades: list, stop_levels: list) -> pd.DataFrame:
    """For each stop-loss level, calculate what P/L would be if we capped losses."""
    results = []
    for stop in stop_levels:
        capped = [max(p, -stop) for p in trades]
        total  = sum(capped)
        winners = sum(1 for p in capped if p > 0)
        losers  = sum(1 for p in capped if p <= 0)
        win_rate = winners / len(capped) * 100 if capped else 0
        results.append({
            "stop_loss": stop,
            "total_pl_pts": round(total, 0),
            "total_pl_usd": round(total * _CONTRACTS * _MULTIPLIER, 0),
            "winners": winners,
            "losers":  losers,
            "win_rate": round(win_rate, 1),
        })
    return pd.DataFrame(results)


def loss_distribution(trades: list) -> None:
    losers = sorted([p for p in trades if p < 0])
    buckets = [(-10,0), (-20,-10), (-30,-20), (-50,-30), (-75,-50),
               (-100,-75), (-150,-100), (-200,-150), (-999,-200)]
    print(f"  {'Range':>18}  {'Count':>6}  {'% of losers':>12}  {'Total pts':>10}")
    total_losers = len(losers)
    for lo, hi in buckets:
        count = sum(1 for p in losers if lo <= p < hi)
        pct   = count / total_losers * 100 if total_losers else 0
        total = sum(p for p in losers if lo <= p < hi)
        label = f"{hi} to {lo}"
        print(f"  {label:>18}  {count:>6}  {pct:>11.1f}%  {total:>10.0f}")


if __name__ == "__main__":
    stop_levels = [20, 30, 40, 50, 60, 75, 100, 150, 999]

    for mins in [5, 6, 7, 8, 9, 10]:
        print(f"\n{'='*70}")
        print(f"TIME FILTER: {mins} minutes")
        print(f"{'='*70}")

        trades = get_all_trades(mins)
        losers = [p for p in trades if p < 0]
        winners = [p for p in trades if p > 0]

        print(f"Total trades: {len(trades)}  "
              f"Winners: {len(winners)}  Losers: {len(losers)}  "
              f"Win%: {len(winners)/len(trades)*100:.1f}%")
        print(f"Total P/L: {sum(trades):+.0f} pts  "
              f"${sum(trades)*_CONTRACTS*_MULTIPLIER:+,.0f}")
        print(f"Avg winner: {np.mean(winners):+.1f} pts   "
              f"Avg loser: {np.mean(losers):+.1f} pts")
        print(f"Worst loss: {min(losers):.0f} pts   "
              f"Best win: {max(winners):.0f} pts")

        print(f"\nLoss distribution:")
        loss_distribution(trades)

        print(f"\nStop-loss analysis (if we cap each loss at X points):")
        sl_df = analyse_stop_loss(trades, stop_levels)
        print(f"  {'Stop':>6}  {'Trades':>7}  {'Win%':>6}  {'P/L pts':>10}  {'P/L USD':>14}")
        print(f"  {'-'*55}")
        for _, row in sl_df.iterrows():
            print(f"  {int(row['stop_loss']):>6}  {len(trades):>7}  "
                  f"{row['win_rate']:>5.1f}%  {row['total_pl_pts']:>10.0f}  "
                  f"${row['total_pl_usd']:>13,.0f}")
