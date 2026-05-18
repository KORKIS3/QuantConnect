"""
run_full_ab_682.py — Full 682-day A/B: Baseline belief engine vs Experiment v2

Captures per-day and per-trade metrics, hourly P/L, worst days analysis,
and first-trade hold behavior across all sessions.
"""
import os
import csv
import time
import numpy as np
import pandas as pd
import pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast
from fred_belief_engine import BeliefEngine, BeliefConfig
from belief_engine_experiment2 import BeliefEngineV2, BeliefConfig2

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")


def _get_config():
    return AlgoConfig(
        warmup_minutes=7,
        steep_angle_threshold=90.0,
        proximity_points=4.0,
        min_reversal_minutes=0,
        min_entry_angle=0.0,
        partial_tp_pts=50.0,
        wm_shield_distance=0.0,
        swing_anchor_threshold=10.0,
    )


def _run_day(fname):
    target_date = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
    fpath = os.path.join(_DATA_ROOT, fname)

    try:
        df = pd.read_csv(fpath, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    except Exception:
        return None

    if len(df) < 10:
        return None

    day_start = pd.Timestamp(f'{target_date} 09:30', tz=_EST)
    day_end = pd.Timestamp(f'{target_date} 16:59', tz=_EST)
    day_data = df[(df.index >= day_start) & (df.index <= day_end)]

    if len(day_data) < 15:
        return None
    if (day_data[["Open", "High", "Low", "Close"]] <= 0).any().any():
        return None
    if day_data["High"].max() == day_data["Low"].min():
        return None
    if day_data["Volume"].sum() < 100:
        return None

    config = _get_config()
    try:
        algo_df = run_trading_algo_fast(day_data, target_date, '09:30', '17:00', config=config)
    except Exception:
        return None

    if algo_df is None or len(algo_df) < 15:
        return None

    # Run baseline belief engine
    try:
        baseline = BeliefEngine(BeliefConfig())
        baseline.run_session(algo_df)
        baseline_pl = baseline.session_pl
        baseline_trades = sum(1 for l in baseline.bar_logs if l['action'] in ('BUY', 'SELL', 'REVERSE'))
    except Exception:
        baseline_pl = 0.0
        baseline_trades = 0

    # Run experiment v2
    try:
        experiment = BeliefEngineV2(BeliefConfig2())
        experiment.run_session(algo_df)
        experiment_pl = experiment.session_pl
        experiment_trades = sum(1 for l in experiment.bar_logs if l['action'] in ('BUY', 'SELL', 'REVERSE'))
        experiment_blocked = len(experiment.blocked_signals)
        experiment_day_type = experiment.day_type
        # Count first-trade holds
        first_trade_holds = sum(1 for bs in experiment.blocked_signals if bs.get('reason') == 'FIRST_TRADE_HOLD')
    except Exception:
        experiment_pl = 0.0
        experiment_trades = 0
        experiment_blocked = 0
        experiment_day_type = "ERROR"
        first_trade_holds = 0

    return {
        'date': target_date,
        'baseline_pl': baseline_pl,
        'experiment_pl': experiment_pl,
        'baseline_trades': baseline_trades,
        'experiment_trades': experiment_trades,
        'blocked': experiment_blocked,
        'day_type': experiment_day_type,
        'first_trade_holds': first_trade_holds,
    }


def main():
    files = sorted([f for f in os.listdir(_DATA_ROOT)
                    if f.startswith('CBOT_MINI_YM1_') and f.endswith('.csv')])
    total = len(files)
    print(f"Running full A/B on {total} files...")

    results = []
    t_start = time.time()

    for i, fname in enumerate(files):
        r = _run_day(fname)
        if r:
            results.append(r)
        if (i + 1) % 100 == 0:
            elapsed = time.time() - t_start
            print(f"  [{i+1}/{total}] {len(results)} valid days, {elapsed:.0f}s")

    elapsed = time.time() - t_start
    n = len(results)
    print(f"\nCompleted: {n} valid days in {elapsed:.1f}s\n")

    # --- Aggregate ---
    b_pls = [r['baseline_pl'] for r in results]
    e_pls = [r['experiment_pl'] for r in results]

    b_total = sum(b_pls)
    e_total = sum(e_pls)
    b_wins = sum(1 for p in b_pls if p > 0)
    e_wins = sum(1 for p in e_pls if p > 0)
    b_trades_total = sum(r['baseline_trades'] for r in results)
    e_trades_total = sum(r['experiment_trades'] for r in results)

    print("=" * 80)
    print(f"{'METRIC':<30} {'BASELINE':>15} {'EXPERIMENT v2':>15} {'DELTA':>12}")
    print("-" * 80)
    print(f"{'Total Days':<30} {n:>15} {n:>15}")
    print(f"{'Total Pts':<30} {b_total:>+15.0f} {e_total:>+15.0f} {e_total-b_total:>+12.0f}")
    print(f"{'Avg Pts/Day':<30} {b_total/n:>+15.1f} {e_total/n:>+15.1f} {(e_total-b_total)/n:>+12.1f}")
    print(f"{'Win Days':<30} {b_wins:>15} {e_wins:>15} {e_wins-b_wins:>+12}")
    print(f"{'Win % (days)':<30} {b_wins/n*100:>14.1f}% {e_wins/n*100:>14.1f}% {(e_wins-b_wins)/n*100:>+11.1f}%")
    print(f"{'Lose Days':<30} {n-b_wins:>15} {n-e_wins:>15} {(n-e_wins)-(n-b_wins):>+12}")
    print(f"{'Total Trades':<30} {b_trades_total:>15} {e_trades_total:>15} {e_trades_total-b_trades_total:>+12}")
    print(f"{'Avg Trades/Day':<30} {b_trades_total/n:>15.1f} {e_trades_total/n:>15.1f}")
    print(f"{'Total Blocked Signals':<30} {'':>15} {sum(r['blocked'] for r in results):>15}")
    print(f"{'First-Trade Holds':<30} {'':>15} {sum(r['first_trade_holds'] for r in results):>15}")
    print("=" * 80)

    # --- Day type breakdown ---
    trend_days = [r for r in results if r['day_type'] == 'TREND']
    chop_days = [r for r in results if r['day_type'] == 'CHOP']
    unknown_days = [r for r in results if r['day_type'] not in ('TREND', 'CHOP')]

    print(f"\n--- DAY TYPE BREAKDOWN ---")
    print(f"{'Type':<10} {'Count':>6} {'B Avg/Day':>10} {'E Avg/Day':>10} {'E Wins':>7}")
    for label, subset in [("TREND", trend_days), ("CHOP", chop_days), ("UNKNOWN", unknown_days)]:
        if not subset:
            continue
        b_avg = sum(r['baseline_pl'] for r in subset) / len(subset)
        e_avg = sum(r['experiment_pl'] for r in subset) / len(subset)
        e_w = sum(1 for r in subset if r['experiment_pl'] > 0)
        print(f"{label:<10} {len(subset):>6} {b_avg:>+10.1f} {e_avg:>+10.1f} {e_w:>7}")

    # --- Top 5 winning / losing days ---
    sorted_by_exp = sorted(results, key=lambda r: r['experiment_pl'])
    print(f"\n--- TOP 5 LOSING DAYS (Experiment) ---")
    for r in sorted_by_exp[:5]:
        print(f"  {r['date']}: exp={r['experiment_pl']:+.0f} base={r['baseline_pl']:+.0f} type={r['day_type']} trades={r['experiment_trades']}")

    print(f"\n--- TOP 5 WINNING DAYS (Experiment) ---")
    for r in sorted_by_exp[-5:]:
        print(f"  {r['date']}: exp={r['experiment_pl']:+.0f} base={r['baseline_pl']:+.0f} type={r['day_type']} trades={r['experiment_trades']}")

    # --- Days where experiment beats baseline by most ---
    deltas = sorted(results, key=lambda r: r['experiment_pl'] - r['baseline_pl'])
    print(f"\n--- TOP 5 DAYS EXPERIMENT BEATS BASELINE ---")
    for r in deltas[-5:]:
        d = r['experiment_pl'] - r['baseline_pl']
        print(f"  {r['date']}: delta={d:+.0f} (exp={r['experiment_pl']:+.0f} base={r['baseline_pl']:+.0f}) type={r['day_type']}")

    print(f"\n--- TOP 5 DAYS BASELINE BEATS EXPERIMENT ---")
    for r in deltas[:5]:
        d = r['experiment_pl'] - r['baseline_pl']
        print(f"  {r['date']}: delta={d:+.0f} (exp={r['experiment_pl']:+.0f} base={r['baseline_pl']:+.0f}) type={r['day_type']}")

    # --- Write CSV for further analysis ---
    with open('full_ab_682_results.csv', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'date', 'baseline_pl', 'experiment_pl', 'baseline_trades',
            'experiment_trades', 'blocked', 'day_type', 'first_trade_holds'
        ])
        writer.writeheader()
        writer.writerows(results)

    print(f"\nDetailed results: full_ab_682_results.csv ({n} rows)")


if __name__ == "__main__":
    main()
