"""
Validate the belief engine against Scott's 6 screenshot sessions.
Runs both the existing mechanical algo AND the belief engine on the same data,
then compares outputs.
"""
import sys, os
sys.path.insert(0, '.')
import pandas as pd, pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast
from fred_belief_engine import BeliefEngine

EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

# Current best config
CONFIG = AlgoConfig(
    warmup_minutes=7,
    steep_angle_threshold=90.0,
    proximity_points=4.0,
    min_reversal_minutes=0,
    min_entry_angle=0.0,
    partial_tp_pts=50.0,
    spike_profit_pts=50.0,
    spike_profit_bars=9,
    wm_shield_distance=0.0,
    steep_line_reentry=False,
    steep_line_proximity=0.0,
    steep_line_exit_only=False,
    num_contracts=2,
)


def load_day(date_str: str, end_time: str = "11:00") -> pd.DataFrame:
    """Load a day's data and run the mechanical algo."""
    fpath = os.path.join(DATA_ROOT, f"CBOT_MINI_YM1_{date_str}.csv")
    if not os.path.exists(fpath):
        print(f"  File not found: {fpath}")
        return None

    df = pd.read_csv(fpath, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(EST)

    day_start = pd.Timestamp(f"{date_str} 09:30", tz=EST)
    day_end = pd.Timestamp(f"{date_str} {end_time}", tz=EST)
    day_data = df[(df.index >= day_start) & (df.index <= day_end)]

    if len(day_data) < 15:
        print(f"  Insufficient data: {len(day_data)} bars")
        return None

    # Run mechanical algo
    algo_df = run_trading_algo_fast(day_data, date_str, "09:30", end_time, config=CONFIG)
    return algo_df


def run_belief_engine_on_day(date_str: str, end_time: str = "11:00"):
    """Run both engines on a day and print comparison."""
    print(f"\n{'='*80}")
    print(f"SESSION: {date_str} (9:30 - {end_time})")
    print(f"{'='*80}")

    algo_df = load_day(date_str, end_time)
    if algo_df is None:
        return None

    # Run belief engine
    engine = BeliefEngine()
    belief_log = engine.run_session(algo_df)

    # Print mechanical algo signals
    mech_signals = algo_df[algo_df['signal'].isin(['BUY', 'SELL'])]
    print(f"\nMECHANICAL ALGO signals: {len(mech_signals)}")
    for idx, row in mech_signals.iterrows():
        print(f"  {idx.strftime('%H:%M')} | {row['signal']:<5} @ {row['Close']:.0f}")

    # Print belief engine actions
    belief_actions = belief_log[belief_log['action'].isin(['BUY', 'SELL', 'REVERSE', 'PARTIAL_TP', 'SPIKE_EXIT'])]
    print(f"\nBELIEF ENGINE actions: {len(belief_actions)}")
    for _, row in belief_actions.iterrows():
        print(f"  {row['time'].strftime('%H:%M') if hasattr(row['time'], 'strftime') else row['time']} | "
              f"{row['action']:<12} | pos={row['position']:+d} | conf={row['confidence']:+.1f} | "
              f"resolve={row['resolve_state']:<12} | PL={row['session_pl']:.0f}")

    # Print final comparison
    print(f"\nFINAL P/L:")
    print(f"  Mechanical: {algo_df.iloc[-1]['session_pl']:.0f} pts")
    print(f"  Belief:     {belief_log.iloc[-1]['session_pl']:.0f} pts")

    return belief_log


if __name__ == "__main__":
    # The 6 screenshot sessions
    sessions = [
        ("2026-02-05", "10:30"),
        ("2026-02-11", "10:30"),
        ("2026-02-13", "10:30"),
        ("2026-02-17", "10:30"),
        ("2026-04-21", "11:00"),
        ("2026-04-23", "11:00"),
    ]

    for date_str, end_time in sessions:
        try:
            run_belief_engine_on_day(date_str, end_time)
        except Exception as e:
            print(f"\n  ERROR on {date_str}: {e}")
            import traceback
            traceback.print_exc()
