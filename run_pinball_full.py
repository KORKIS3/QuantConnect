"""
run_pinball_full.py — Full 682-day Pinball backtest

Runs the PinballEngine on all available days, outputs per-day and per-trade CSVs.
"""
import os
import time
import csv
import pandas as pd
import pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast
from belief_engine_pinball import PinballEngine, PinballConfig

_EST = pytz.timezone("US/Eastern")
DATA_ROOT = os.path.expanduser('~/Desktop/2YearsData/full_day')
OUTPUT_CSV = "full_pinball_682_results.csv"
PER_TRADE_CSV = "full_pinball_682_trades.csv"


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
    fpath = os.path.join(DATA_ROOT, fname)

    try:
        df = pd.read_csv(fpath, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    except Exception:
        return None, []

    if len(df) < 10:
        return None, []

    day_start = pd.Timestamp(f'{target_date} 09:30', tz=_EST)
    day_end = pd.Timestamp(f'{target_date} 16:59', tz=_EST)
    day_data = df[(df.index >= day_start) & (df.index <= day_end)]

    if len(day_data) < 15:
        return None, []
    if (day_data[["Open", "High", "Low", "Close"]] <= 0).any().any():
        return None, []
    if day_data["High"].max() == day_data["Low"].min():
        return None, []
    if day_data["Volume"].sum() < 100:
        return None, []

    config = _get_config()
    try:
        algo_df = run_trading_algo_fast(day_data, target_date, '09:30', '17:00', config=config)
    except Exception:
        return None, []

    if algo_df is None or len(algo_df) < 15:
        return None, []

    # Run Pinball engine
    try:
        engine = PinballEngine(PinballConfig())
        engine.run_session(algo_df)
    except Exception:
        return None, []

    # Day summary
    day_summary = {
        'date': target_date,
        'total_pts': engine.session_pl,
        'trades': engine.trade_count,
        'mode': engine.mode,
        'blocked': len(engine.blocked_signals),
        'first_trade_holds': sum(1 for bs in engine.blocked_signals if bs.get('reason') == 'FIRST_TRADE_HOLD'),
    }

    # Per-trade detail
    trades = engine.trades
    for t in trades:
        t['session_date'] = target_date

    return day_summary, trades


def main():
    files = sorted([f for f in os.listdir(DATA_ROOT)
                    if f.startswith('CBOT_MINI_YM1_') and f.endswith('.csv')])
    total = len(files)
    print(f"Running Pinball backtest on {total} files...")

    day_results = []
    all_trades = []
    t_start = time.time()

    for i, fname in enumerate(files):
        day_summary, trades = _run_day(fname)
        if day_summary:
            day_results.append(day_summary)
            all_trades.extend(trades)
        if (i + 1) % 100 == 0:
            elapsed = time.time() - t_start
            print(f"  [{i+1}/{total}] {len(day_results)} valid days, {elapsed:.0f}s")

    elapsed = time.time() - t_start
    n = len(day_results)
    print(f"\nCompleted: {n} valid days in {elapsed:.1f}s")

    # Save CSVs
    day_df = pd.DataFrame(day_results)
    day_df.to_csv(OUTPUT_CSV, index=False)

    if all_trades:
        trade_df = pd.DataFrame(all_trades)
        trade_df.to_csv(PER_TRADE_CSV, index=False)
    else:
        trade_df = pd.DataFrame()

    # Summary
    total_pts = day_df['total_pts'].sum()
    avg_pts = day_df['total_pts'].mean()
    win_days = (day_df['total_pts'] > 0).sum()
    lose_days = (day_df['total_pts'] <= 0).sum()
    median_pts = day_df['total_pts'].median()

    print(f"\n{'='*70}")
    print(f"FULL PINBALL BACKTEST — {n} days")
    print(f"{'='*70}")
    print(f"Total Pts:     {total_pts:+.0f}")
    print(f"Avg Pts/Day:   {avg_pts:+.1f}")
    print(f"Median Pts:    {median_pts:+.0f}")
    print(f"Win Days:      {win_days} ({win_days/n*100:.1f}%)")
    print(f"Lose Days:     {lose_days} ({lose_days/n*100:.1f}%)")
    print(f"Total Trades:  {len(all_trades)}")
    print(f"Avg Trades/Day:{len(all_trades)/n:.1f}")
    print(f"Best Day:      {day_df['total_pts'].max():+.0f}")
    print(f"Worst Day:     {day_df['total_pts'].min():+.0f}")

    # Day type breakdown
    print(f"\n--- DAY TYPE BREAKDOWN ---")
    for mode in day_df['mode'].unique():
        subset = day_df[day_df['mode'] == mode]
        print(f"  {mode}: {len(subset)} days, avg={subset['total_pts'].mean():+.1f}/day, "
              f"win={( subset['total_pts'] > 0).sum()}/{len(subset)}")

    # Top/bottom days
    sorted_days = day_df.sort_values('total_pts')
    print(f"\n--- TOP 5 LOSING DAYS ---")
    for _, r in sorted_days.head(5).iterrows():
        print(f"  {r['date']}: {r['total_pts']:+.0f} pts, {r['trades']} trades, mode={r['mode']}")

    print(f"\n--- TOP 5 WINNING DAYS ---")
    for _, r in sorted_days.tail(5).iterrows():
        print(f"  {r['date']}: {r['total_pts']:+.0f} pts, {r['trades']} trades, mode={r['mode']}")

    # Trade type breakdown
    if not trade_df.empty and 'trade_type' in trade_df.columns:
        print(f"\n--- TRADE TYPE BREAKDOWN ---")
        for tt in trade_df['trade_type'].unique():
            subset = trade_df[trade_df['trade_type'] == tt]
            if 'realized_pl' in subset.columns:
                total_pl = subset['realized_pl'].sum()
                avg_pl = subset['realized_pl'].mean()
                wins = (subset['realized_pl'] > 0).sum()
                print(f"  {tt}: {len(subset)} trades, total={total_pl:+.0f}, avg={avg_pl:+.1f}, win={wins}/{len(subset)}")

    print(f"\nCSVs: {OUTPUT_CSV}, {PER_TRADE_CSV}")


if __name__ == "__main__":
    main()
