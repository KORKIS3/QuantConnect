"""
run_ab_test_v2.py — A/B test: baseline belief engine vs experiment v2

Compares fred_belief_engine.py (baseline) vs belief_engine_experiment2.py
on 6 verification sessions.
"""
import os
import pandas as pd
import pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast
from fred_belief_engine import BeliefEngine, BeliefConfig
from belief_engine_experiment2 import BeliefEngineV2, BeliefConfig2

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

TEST_DATES = ['2026-02-05', '2026-02-11', '2026-02-13', '2026-02-17', '2025-04-21', '2025-04-23']

# Scott's known results for reference
SCOTT_PL = {
    '2026-02-05': 353,
    '2026-02-11': 362,
    '2026-02-13': -48,
    '2026-02-17': -48,
    '2025-04-21': None,  # unknown
    '2025-04-23': None,  # unknown
}


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


def _run_day(target_date):
    """Run algo and both belief engines on a single day."""
    fname = f'CBOT_MINI_YM1_{target_date}.csv'
    fpath = os.path.join(_DATA_ROOT, fname)

    if not os.path.exists(fpath):
        return None

    df = pd.read_csv(fpath, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)

    day_start = pd.Timestamp(f'{target_date} 09:30', tz=_EST)
    day_end = pd.Timestamp(f'{target_date} 16:59', tz=_EST)
    day_data = df[(df.index >= day_start) & (df.index <= day_end)]

    if len(day_data) < 15:
        return None

    config = _get_config()
    algo_df = run_trading_algo_fast(day_data, target_date, '09:30', '17:00', config=config)

    if algo_df is None or len(algo_df) < 15:
        return None

    # Run baseline
    baseline = BeliefEngine(BeliefConfig())
    baseline_result = baseline.run_session(algo_df)
    baseline_pl = baseline.session_pl

    # Run experiment v2
    experiment = BeliefEngineV2(BeliefConfig2())
    experiment_result = experiment.run_session(algo_df)
    experiment_pl = experiment.session_pl

    # Count trades (non-HOLD, non-WAIT actions)
    baseline_trades = len([l for l in baseline.bar_logs if l['action'] in ('BUY', 'SELL', 'REVERSE')])
    experiment_trades = len([l for l in experiment.bar_logs if l['action'] in ('BUY', 'SELL', 'REVERSE')])

    # Count blocked signals
    blocked = len(experiment.blocked_signals)

    return {
        'date': target_date,
        'baseline_pl': baseline_pl,
        'experiment_pl': experiment_pl,
        'baseline_trades': baseline_trades,
        'experiment_trades': experiment_trades,
        'blocked_signals': blocked,
        'blocked_details': experiment.blocked_signals,
    }


def main():
    print("=" * 90)
    print("A/B TEST: Baseline Belief Engine vs Experiment v2 (Session Discipline)")
    print("=" * 90)
    print(f"{'Date':<12} {'Scott':>7} {'Baseline':>10} {'Exp v2':>10} {'B Trades':>9} {'E Trades':>9} {'Blocked':>8} {'Winner':>8}")
    print("-" * 90)

    total_baseline = 0
    total_experiment = 0

    for target_date in TEST_DATES:
        result = _run_day(target_date)
        if result is None:
            print(f"{target_date:<12} {'N/A':>7} {'N/A':>10} {'N/A':>10}")
            continue

        scott = SCOTT_PL.get(target_date)
        scott_str = f"{scott:+.0f}" if scott is not None else "?"

        b_pl = result['baseline_pl']
        e_pl = result['experiment_pl']
        total_baseline += b_pl
        total_experiment += e_pl

        winner = "EXP" if e_pl > b_pl else "BASE" if b_pl > e_pl else "TIE"

        print(f"{target_date:<12} {scott_str:>7} {b_pl:>+10.0f} {e_pl:>+10.0f} "
              f"{result['baseline_trades']:>9} {result['experiment_trades']:>9} "
              f"{result['blocked_signals']:>8} {winner:>8}")

        # Show blocked signal details
        if result['blocked_details']:
            for bs in result['blocked_details'][:3]:
                t = bs['time'].strftime('%H:%M') if hasattr(bs['time'], 'strftime') else str(bs['time'])
                print(f"  BLOCKED: {t} {bs['action']} — {bs['reason']} ({bs['evidence']})")

    print("-" * 90)
    print(f"{'TOTAL':<12} {'':>7} {total_baseline:>+10.0f} {total_experiment:>+10.0f}")
    print(f"{'AVG/DAY':<12} {'':>7} {total_baseline/len(TEST_DATES):>+10.1f} {total_experiment/len(TEST_DATES):>+10.1f}")
    print()

    # Summary
    print("KEY CHANGES IN EXPERIMENT v2:")
    print("  1. warmup_bars: 7 → 12 (delays first entry)")
    print("  2. min_reversal_minutes: 0 → 5 (prevents whipsaws)")
    print("  3. session_end: 10:30 hard exit + one-and-done")
    print("  4. first_entry_trend_filter: must match slope direction")


if __name__ == "__main__":
    main()
