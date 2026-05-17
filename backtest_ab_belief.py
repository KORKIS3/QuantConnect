"""
backtest_ab_belief.py — A/B Test: Baseline vs Experiment Belief Engine

Runs both belief engines on every day in the 680-day dataset and produces:
- Per-day P/L comparison (baseline vs experiment)
- Per-hour P/L breakdown
- Win/loss day counts
- Max drawdown
- Cumulative P/L curves
- CSV output for further analysis
"""

import argparse
import os
import sys
import time
import numpy as np
import pandas as pd
import pytz
from datetime import datetime

from TradingAlgoFast import AlgoConfig, run_trading_algo_fast
from fred_belief_engine import BeliefEngine, BeliefConfig as BaselineConfig
from belief_engine_experiment import BeliefEngineExperiment, BeliefConfig as ExperimentConfig

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")
_MULTIPLIER = 5  # $5/pt for YM


def _get_algo_config():
    """Identical config to Backtest2Year.py — single source of truth."""
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


def _run_day(fname: str):
    """Run both engines on a single day. Returns dict with results or None on failure."""
    target_date = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
    fpath = os.path.join(_DATA_ROOT, fname)

    try:
        df = pd.read_csv(fpath, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    except Exception:
        return None

    if len(df) < 10:
        return None

    # Filter to day session 9:30–17:00
    day_start = pd.Timestamp(f"{target_date} 09:30", tz=_EST)
    day_end = pd.Timestamp(f"{target_date} 16:59", tz=_EST)
    day_data = df[(df.index >= day_start) & (df.index <= day_end)]

    if len(day_data) < 15:
        return None

    # Guard: skip bad data
    if (day_data[["Open", "High", "Low", "Close"]] <= 0).any().any():
        return None
    if day_data["High"].max() == day_data["Low"].min():
        return None
    if day_data["Volume"].sum() < 100:
        return None

    # Run mechanical algo
    config = _get_algo_config()
    try:
        algo_df = run_trading_algo_fast(day_data, target_date, "09:30", "17:00", config=config)
    except Exception:
        return None

    if algo_df is None or len(algo_df) < 15:
        return None

    # --- Run baseline belief engine ---
    baseline_engine = BeliefEngine(BaselineConfig())
    try:
        baseline_result = baseline_engine.run_session(algo_df)
    except Exception:
        return None

    # --- Run experiment belief engine ---
    experiment_engine = BeliefEngineExperiment(ExperimentConfig())
    try:
        experiment_result = experiment_engine.run_session(algo_df)
    except Exception:
        return None

    # Extract final session P/L
    baseline_pl = baseline_engine.session_pl
    experiment_pl = experiment_engine.session_pl

    # Per-hour P/L breakdown
    hour_pls_baseline = _compute_hourly_pl(baseline_result, target_date)
    hour_pls_experiment = _compute_hourly_pl(experiment_result, target_date)

    return {
        "date": target_date,
        "baseline_pl": baseline_pl,
        "experiment_pl": experiment_pl,
        "baseline_trades": len(baseline_engine.evidence_log),
        "experiment_trades": len(experiment_engine.trades),
        "hour_pls_baseline": hour_pls_baseline,
        "hour_pls_experiment": hour_pls_experiment,
    }


def _compute_hourly_pl(result_df: pd.DataFrame, target_date: str) -> dict:
    """Compute P/L at the end of each hour from the bar log."""
    hours = {}
    if result_df.empty:
        return hours

    for hour in range(9, 17):
        # Find the last bar in this hour
        hour_end = pd.Timestamp(f"{target_date} {hour:02d}:59", tz=_EST)
        hour_start = pd.Timestamp(f"{target_date} {hour:02d}:00", tz=_EST)

        # Get session_pl at end of this hour
        mask = result_df["time"] <= hour_end
        if mask.any():
            pl_at_hour_end = float(result_df.loc[mask, "session_pl"].iloc[-1])
        else:
            pl_at_hour_end = 0.0

        # Get session_pl at start of this hour (end of previous hour)
        mask_prev = result_df["time"] < hour_start
        if mask_prev.any():
            pl_at_hour_start = float(result_df.loc[mask_prev, "session_pl"].iloc[-1])
        else:
            pl_at_hour_start = 0.0

        hours[f"{hour:02d}:00"] = pl_at_hour_end - pl_at_hour_start

    return hours


def _max_drawdown(daily_pls: list) -> float:
    """Compute max drawdown from a list of daily P/Ls."""
    if not daily_pls:
        return 0.0
    cumulative = np.cumsum(daily_pls)
    peak = np.maximum.accumulate(cumulative)
    drawdown = cumulative - peak
    return float(np.min(drawdown))


def run_ab_test(max_days: int = 0):
    """Run the full A/B test across all available days."""
    csv_files = sorted([f for f in os.listdir(_DATA_ROOT)
                        if f.startswith("CBOT_MINI_YM1_") and f.endswith(".csv")])
    if max_days > 0:
        csv_files = csv_files[-max_days:]

    total = len(csv_files)
    t_start = time.time()
    print(f"\n{'='*80}")
    print(f"A/B TEST: Baseline Belief Engine vs Experiment (Noon Stop + Afternoon Re-entry)")
    print(f"{'='*80}")
    print(f"Days to process: {total}")
    print(f"Data: {_DATA_ROOT}\n")

    results = []
    done = 0

    for fname in csv_files:
        done += 1
        if done % 20 == 0 or done == total:
            elapsed = time.time() - t_start
            rate = done / elapsed if elapsed > 0 else 0
            eta = (total - done) / rate if rate > 0 else 0
            print(f"  [{done}/{total}] {done/total*100:.0f}% — {elapsed:.0f}s elapsed, ~{eta:.0f}s remaining — {len(results)} valid days so far", flush=True)

        day_result = _run_day(fname)
        if day_result:
            results.append(day_result)

    elapsed = time.time() - t_start
    print(f"\nProcessed {len(results)} valid days in {elapsed:.1f}s\n")

    if not results:
        print("No valid results. Check data path.")
        return

    # --- Aggregate results ---
    baseline_pls = [r["baseline_pl"] for r in results]
    experiment_pls = [r["experiment_pl"] for r in results]

    baseline_total = sum(baseline_pls)
    experiment_total = sum(experiment_pls)
    baseline_avg = np.mean(baseline_pls)
    experiment_avg = np.mean(experiment_pls)

    baseline_win_days = sum(1 for p in baseline_pls if p > 0)
    experiment_win_days = sum(1 for p in experiment_pls if p > 0)
    baseline_lose_days = sum(1 for p in baseline_pls if p <= 0)
    experiment_lose_days = sum(1 for p in experiment_pls if p <= 0)

    baseline_win_pct = baseline_win_days / len(baseline_pls) * 100
    experiment_win_pct = experiment_win_days / len(experiment_pls) * 100

    baseline_max_dd = _max_drawdown(baseline_pls)
    experiment_max_dd = _max_drawdown(experiment_pls)

    # --- Print summary ---
    print(f"{'='*80}")
    print(f"{'METRIC':<30} {'BASELINE':>15} {'EXPERIMENT':>15} {'DELTA':>12}")
    print(f"{'-'*80}")
    print(f"{'Total Days':<30} {len(results):>15} {len(results):>15} {'—':>12}")
    print(f"{'Total Pts':<30} {baseline_total:>15,.0f} {experiment_total:>15,.0f} {experiment_total-baseline_total:>+12,.0f}")
    print(f"{'Total P/L (USD)':<30} ${baseline_total*_MULTIPLIER:>14,.0f} ${experiment_total*_MULTIPLIER:>14,.0f} ${(experiment_total-baseline_total)*_MULTIPLIER:>+11,.0f}")
    print(f"{'Avg Pts/Day':<30} {baseline_avg:>+15.1f} {experiment_avg:>+15.1f} {experiment_avg-baseline_avg:>+12.1f}")
    print(f"{'Win Days':<30} {baseline_win_days:>15} {experiment_win_days:>15} {experiment_win_days-baseline_win_days:>+12}")
    print(f"{'Lose Days':<30} {baseline_lose_days:>15} {experiment_lose_days:>15} {experiment_lose_days-baseline_lose_days:>+12}")
    print(f"{'Win %':<30} {baseline_win_pct:>14.1f}% {experiment_win_pct:>14.1f}% {experiment_win_pct-baseline_win_pct:>+11.1f}%")
    print(f"{'Max Drawdown (pts)':<30} {baseline_max_dd:>15,.0f} {experiment_max_dd:>15,.0f} {experiment_max_dd-baseline_max_dd:>+12,.0f}")
    print(f"{'='*80}")

    # --- Per-hour P/L breakdown ---
    print(f"\n{'='*80}")
    print(f"PER-HOUR P/L BREAKDOWN (avg pts/day)")
    print(f"{'HOUR':<10} {'BASELINE':>12} {'EXPERIMENT':>12} {'DELTA':>10}")
    print(f"{'-'*50}")

    for hour in range(9, 17):
        key = f"{hour:02d}:00"
        b_hourly = [r["hour_pls_baseline"].get(key, 0.0) for r in results]
        e_hourly = [r["hour_pls_experiment"].get(key, 0.0) for r in results]
        b_avg = np.mean(b_hourly) if b_hourly else 0
        e_avg = np.mean(e_hourly) if e_hourly else 0
        print(f"{key:<10} {b_avg:>+12.1f} {e_avg:>+12.1f} {e_avg-b_avg:>+10.1f}")

    print(f"{'='*80}")

    # --- Save detailed CSV ---
    output_rows = []
    for r in results:
        row = {
            "date": r["date"],
            "baseline_pl": r["baseline_pl"],
            "experiment_pl": r["experiment_pl"],
            "delta_pl": r["experiment_pl"] - r["baseline_pl"],
        }
        for hour in range(9, 17):
            key = f"{hour:02d}:00"
            row[f"baseline_{key}"] = r["hour_pls_baseline"].get(key, 0.0)
            row[f"experiment_{key}"] = r["hour_pls_experiment"].get(key, 0.0)
        output_rows.append(row)

    out_df = pd.DataFrame(output_rows)
    out_path = "ab_test_belief_results.csv"
    out_df.to_csv(out_path, index=False)
    print(f"\nDetailed results saved to: {out_path}")

    # --- Days where experiment beats baseline by most ---
    out_df["delta_pl"] = out_df["experiment_pl"] - out_df["baseline_pl"]
    top_wins = out_df.nlargest(10, "delta_pl")
    top_losses = out_df.nsmallest(10, "delta_pl")

    print(f"\nTOP 10 DAYS EXPERIMENT WINS:")
    print(f"{'Date':<12} {'Baseline':>10} {'Experiment':>12} {'Delta':>10}")
    for _, row in top_wins.iterrows():
        print(f"{row['date']:<12} {row['baseline_pl']:>+10.0f} {row['experiment_pl']:>+12.0f} {row['delta_pl']:>+10.0f}")

    print(f"\nTOP 10 DAYS BASELINE WINS:")
    print(f"{'Date':<12} {'Baseline':>10} {'Experiment':>12} {'Delta':>10}")
    for _, row in top_losses.iterrows():
        print(f"{row['date']:<12} {row['baseline_pl']:>+10.0f} {row['experiment_pl']:>+12.0f} {row['delta_pl']:>+10.0f}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="A/B Test: Belief Engine Baseline vs Experiment")
    p.add_argument("--max-days", type=int, default=0, dest="max_days",
                   help="Limit to last N days (0 = all)")
    args = p.parse_args()
    run_ab_test(max_days=args.max_days)
