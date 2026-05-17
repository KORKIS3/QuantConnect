"""
run_ab_test_v2.py — A/B test: baseline belief engine vs experiment v2

Compares fred_belief_engine.py (baseline) vs belief_engine_experiment2.py
on 6 verification sessions with detailed per-trade and blocked signal analysis.
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

SCOTT_PL = {
    '2026-02-05': 353,
    '2026-02-11': 362,
    '2026-02-13': -48,
    '2026-02-17': -48,
    '2025-04-21': None,
    '2025-04-23': None,
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

    # Extract trade actions from logs
    baseline_actions = [l for l in baseline.bar_logs if l['action'] in ('BUY', 'SELL', 'REVERSE', 'PARTIAL_TP', 'SPIKE_EXIT')]
    experiment_actions = [l for l in experiment.bar_logs if l['action'] in ('BUY', 'SELL', 'REVERSE', 'PARTIAL_TP', 'SPIKE_EXIT', 'SESSION_EXIT')]

    return {
        'date': target_date,
        'baseline_pl': baseline_pl,
        'experiment_pl': experiment_pl,
        'baseline_actions': baseline_actions,
        'experiment_actions': experiment_actions,
        'blocked_signals': experiment.blocked_signals,
    }


def main():
    print("=" * 95)
    print("A/B TEST: Baseline Belief Engine vs Experiment v2")
    print("Exp v2: warmup=12, cooldown=3min, session_end=10:30 (profit>50 runs), one_and_done, trend_filter")
    print("=" * 95)
    print(f"{'Date':<12} {'Scott':>7} {'Baseline':>10} {'Exp v2':>10} {'B Acts':>7} {'E Acts':>7} {'Blocked':>8} {'Winner':>8}")
    print("-" * 95)

    total_baseline = 0
    total_experiment = 0
    all_results = []

    for target_date in TEST_DATES:
        result = _run_day(target_date)
        if result is None:
            print(f"{target_date:<12} {'N/A':>7}")
            continue

        all_results.append(result)
        scott = SCOTT_PL.get(target_date)
        scott_str = f"{scott:+.0f}" if scott is not None else "?"

        b_pl = result['baseline_pl']
        e_pl = result['experiment_pl']
        total_baseline += b_pl
        total_experiment += e_pl

        b_acts = len(result['baseline_actions'])
        e_acts = len(result['experiment_actions'])
        blocked = len(result['blocked_signals'])
        winner = "EXP" if e_pl > b_pl else "BASE" if b_pl > e_pl else "TIE"

        print(f"{target_date:<12} {scott_str:>7} {b_pl:>+10.0f} {e_pl:>+10.0f} "
              f"{b_acts:>7} {e_acts:>7} {blocked:>8} {winner:>8}")

    print("-" * 95)
    n = len(all_results)
    print(f"{'TOTAL':<12} {'':>7} {total_baseline:>+10.0f} {total_experiment:>+10.0f}")
    print(f"{'AVG/DAY':<12} {'':>7} {total_baseline/n:>+10.1f} {total_experiment/n:>+10.1f}")

    # --- Detailed per-day breakdown ---
    print("\n")
    for result in all_results:
        date = result['date']
        print(f"{'='*80}")
        print(f"  {date}  |  Baseline: {result['baseline_pl']:+.0f}  |  Experiment: {result['experiment_pl']:+.0f}")
        print(f"{'='*80}")

        # Experiment trades
        if result['experiment_actions']:
            print(f"  EXPERIMENT TRADES:")
            for a in result['experiment_actions']:
                t = a['time'].strftime('%H:%M') if hasattr(a['time'], 'strftime') else str(a['time'])
                print(f"    {t} {a['action']:<12} close={a['close']:.0f} pos={a['position']} pl={a['session_pl']:+.0f}")

        # Blocked signals
        if result['blocked_signals']:
            print(f"  BLOCKED SIGNALS ({len(result['blocked_signals'])}):")
            for bs in result['blocked_signals']:
                t = bs['time'].strftime('%H:%M') if hasattr(bs['time'], 'strftime') else str(bs['time'])
                unreal = bs.get('unrealized_pl', 0)
                print(f"    {t} {bs['action']:<20} reason={bs['reason']:<15} evidence={bs.get('evidence','')} unreal_pl={unreal:+.0f}")

        print()

    # Summary
    print("=" * 95)
    print("CONFIG CHANGES FROM BASELINE:")
    print("  warmup_bars: 7 → 12")
    print("  min_reversal_minutes: 0 → 3")
    print("  session_end: 10:30 (trades >50pts profit allowed to run)")
    print("  one_and_done: True (no re-entry after first exit)")
    print("  first_entry_trend_filter: True (first entry must match slope)")


if __name__ == "__main__":
    main()
