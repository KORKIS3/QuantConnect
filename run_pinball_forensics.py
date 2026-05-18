"""
run_pinball_forensics.py — EXIT_FLAT forensic analysis + Opportunity Window analysis

No code changes. Analysis only.
"""
import os, time, csv
import numpy as np
import pandas as pd
import pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast
from belief_engine_pinball import PinballEngine, PinballConfig

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")


def _get_config():
    return AlgoConfig(warmup_minutes=7, steep_angle_threshold=90.0, proximity_points=4.0,
        min_reversal_minutes=0, min_entry_angle=0.0, partial_tp_pts=50.0,
        wm_shield_distance=0.0, swing_anchor_threshold=10.0)


def _run_day_detailed(fname):
    """Run Pinball on a day and return detailed bar-by-bar + trade data."""
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

    engine = PinballEngine(PinballConfig())
    engine.run_session(algo_df)

    return {
        'date': target_date,
        'engine': engine,
        'algo_df': algo_df,
        'bar_logs': engine.bar_logs,
        'trades': engine.trades,
        'blocked': engine.blocked_signals,
        'session_pl': engine.session_pl,
    }


def _compute_excursions(bar_logs, entry_bar_idx, exit_bar_idx, direction):
    """Compute max favorable and adverse excursion between entry and exit."""
    max_favorable = 0.0
    max_adverse = 0.0
    entry_price = 0.0

    for log in bar_logs:
        if log['bar_idx'] == entry_bar_idx:
            entry_price = log['close']
        if entry_bar_idx <= log['bar_idx'] <= exit_bar_idx and entry_price > 0:
            if direction == 'long':
                move = log['close'] - entry_price
            else:
                move = entry_price - log['close']
            if move > max_favorable:
                max_favorable = move
            if move < max_adverse:
                max_adverse = move

    return max_favorable, max_adverse


def _time_bucket(time_str):
    """Convert HH:MM:SS to 30-min bucket."""
    h, m = int(time_str[:2]), int(time_str[3:5])
    total_min = h * 60 + m
    # Buckets start at 9:30
    bucket_start = 9 * 60 + 30
    bucket_idx = (total_min - bucket_start) // 30
    bucket_h = (bucket_start + bucket_idx * 30) // 60
    bucket_m = (bucket_start + bucket_idx * 30) % 60
    end_h = (bucket_start + (bucket_idx + 1) * 30) // 60
    end_m = (bucket_start + (bucket_idx + 1) * 30) % 60
    return f"{bucket_h:02d}:{bucket_m:02d}-{end_h:02d}:{end_m:02d}"


def main():
    files = sorted([f for f in os.listdir(_DATA_ROOT)
                    if f.startswith('CBOT_MINI_YM1_') and f.endswith('.csv')])
    total = len(files)
    print(f"Running Pinball forensics on {total} files...")

    all_exit_flats = []
    all_trades_with_windows = []
    t_start = time.time()
    valid_days = 0

    for i, fname in enumerate(files):
        result = _run_day_detailed(fname)
        if result is None:
            continue
        valid_days += 1

        trades = result['trades']
        bar_logs = result['bar_logs']
        target_date = result['date']

        # Track open positions to pair entries with exits
        open_entry = None
        for t in trades:
            trade_type = t.get('trade_type', '')
            trade_time = t.get('time', '')
            if isinstance(trade_time, str) and len(trade_time) >= 8:
                time_str = trade_time
            elif hasattr(trade_time, 'strftime'):
                time_str = trade_time.strftime('%H:%M:%S')
            else:
                time_str = str(trade_time)

            # Track entry
            if trade_type in ('CHOP_BUY', 'CHOP_SELL', 'TREND_LONG', 'TREND_SHORT'):
                open_entry = {
                    'entry_time': time_str,
                    'entry_type': trade_type,
                    'entry_price': t.get('exit_price', 0),  # entry price stored in exit_price for entries
                    'direction': t.get('direction', ''),
                    'entry_bar_idx': t.get('bars_held', 0),  # approximate
                }
            elif trade_type == 'REVERSE':
                open_entry = {
                    'entry_time': time_str,
                    'entry_type': 'REVERSE',
                    'entry_price': t.get('exit_price', 0),
                    'direction': t.get('direction', ''),
                    'entry_bar_idx': 0,
                }

            # Window analysis: every trade gets a time bucket
            all_trades_with_windows.append({
                'date': target_date,
                'time': time_str,
                'time_bucket': _time_bucket(time_str) if len(time_str) >= 5 else 'UNKNOWN',
                'trade_type': trade_type,
                'direction': t.get('direction', ''),
                'realized_pl': t.get('realized_pl', 0.0),
                'contracts': t.get('contracts', 0),
                'bars_held': t.get('bars_held', 0),
                'day_type': t.get('day_type', ''),
                'mode': t.get('mode', ''),
            })

            # EXIT_FLAT forensics
            if trade_type == 'EXIT_FLAT':
                entry_time = open_entry['entry_time'] if open_entry else ''
                entry_type = open_entry['entry_type'] if open_entry else ''
                entry_price = open_entry['entry_price'] if open_entry else 0
                direction = t.get('direction', '')

                # Compute excursions from bar logs
                max_fav, max_adv = 0.0, 0.0
                # Find entry and exit bar indices
                entry_idx = 0
                exit_idx = 0
                for bl in bar_logs:
                    bl_time = bl['time'].strftime('%H:%M:%S') if hasattr(bl['time'], 'strftime') else ''
                    if bl_time == entry_time:
                        entry_idx = bl['bar_idx']
                    if bl_time == time_str:
                        exit_idx = bl['bar_idx']

                if entry_idx > 0 and exit_idx > entry_idx:
                    max_fav, max_adv = _compute_excursions(bar_logs, entry_idx, exit_idx, direction)

                # Check if partial TP happened
                partial_before = any(
                    tr.get('trade_type') == 'PARTIAL_TP' and tr.get('time', '') < trade_time
                    for tr in trades
                )

                # Check if hard stop caused exit
                hard_stop = (t.get('realized_pl', 0) <= -55)  # close to -60 threshold

                all_exit_flats.append({
                    'date': target_date,
                    'entry_time': entry_time,
                    'exit_time': time_str,
                    'direction': direction,
                    'entry_price': entry_price,
                    'exit_price': t.get('exit_price', 0),
                    'realized_pl': t.get('realized_pl', 0.0),
                    'max_favorable_excursion': max_fav,
                    'max_adverse_excursion': max_adv,
                    'bars_held': t.get('bars_held', 0),
                    'day_type': t.get('day_type', ''),
                    'entry_type': entry_type,
                    'partial_tp_before': partial_before,
                    'hard_stop_exit': hard_stop,
                    'time_bucket': _time_bucket(time_str) if len(time_str) >= 5 else 'UNKNOWN',
                })

        if (i + 1) % 100 == 0:
            print(f"  [{i+1}/{total}] {valid_days} valid days, {time.time()-t_start:.0f}s")

    elapsed = time.time() - t_start
    print(f"\nCompleted: {valid_days} days in {elapsed:.1f}s")
    print(f"EXIT_FLAT trades found: {len(all_exit_flats)}")
    print(f"Total trades for window analysis: {len(all_trades_with_windows)}")

    # === SAVE EXIT_FLAT FORENSICS CSV ===
    ef_df = pd.DataFrame(all_exit_flats)
    ef_df.to_csv('pinball_exit_flat_forensics.csv', index=False)

    # === EXIT_FLAT SUMMARY ===
    print("\n" + "=" * 80)
    print("EXIT_FLAT FORENSIC SUMMARY")
    print("=" * 80)

    if len(all_exit_flats) > 0:
        ef_df_sorted = ef_df.sort_values('realized_pl')
        total_loss = ef_df['realized_pl'].sum()
        avg_loss = ef_df['realized_pl'].mean()
        median_loss = ef_df['realized_pl'].median()

        print(f"Total EXIT_FLAT trades: {len(ef_df)}")
        print(f"Total P/L: {total_loss:+.0f}")
        print(f"Avg P/L: {avg_loss:+.1f}")
        print(f"Median P/L: {median_loss:+.1f}")
        print(f"Worst: {ef_df['realized_pl'].min():+.0f}")
        print(f"Best: {ef_df['realized_pl'].max():+.0f}")

        # By entry type
        print(f"\n--- BY ENTRY TYPE ---")
        for et in ef_df['entry_type'].unique():
            subset = ef_df[ef_df['entry_type'] == et]
            print(f"  {et}: {len(subset)} trades, avg={subset['realized_pl'].mean():+.1f}, total={subset['realized_pl'].sum():+.0f}")

        # By time bucket
        print(f"\n--- BY TIME BUCKET ---")
        for tb in sorted(ef_df['time_bucket'].unique()):
            subset = ef_df[ef_df['time_bucket'] == tb]
            print(f"  {tb}: {len(subset)} trades, avg={subset['realized_pl'].mean():+.1f}, total={subset['realized_pl'].sum():+.0f}")

        # By day type
        print(f"\n--- BY DAY TYPE ---")
        for dt in ef_df['day_type'].unique():
            subset = ef_df[ef_df['day_type'] == dt]
            print(f"  {dt}: {len(subset)} trades, avg={subset['realized_pl'].mean():+.1f}, total={subset['realized_pl'].sum():+.0f}")

        # Hard stop vs evidence-based
        hard_stops = ef_df[ef_df['hard_stop_exit'] == True]
        evidence_exits = ef_df[ef_df['hard_stop_exit'] == False]
        print(f"\n--- HARD STOP vs EVIDENCE EXIT ---")
        print(f"  Hard stop (-60): {len(hard_stops)} trades, avg={hard_stops['realized_pl'].mean():+.1f}, total={hard_stops['realized_pl'].sum():+.0f}")
        print(f"  Evidence-based: {len(evidence_exits)} trades, avg={evidence_exits['realized_pl'].mean():+.1f}, total={evidence_exits['realized_pl'].sum():+.0f}")

        # Max favorable excursion analysis
        print(f"\n--- MAX FAVORABLE EXCURSION (before exit) ---")
        print(f"  Avg MFE: {ef_df['max_favorable_excursion'].mean():+.1f}")
        print(f"  Trades with MFE > 30 (had profit, gave it back): {(ef_df['max_favorable_excursion'] > 30).sum()}")
        print(f"  Trades with MFE < 5 (never profitable): {(ef_df['max_favorable_excursion'] < 5).sum()}")

        # Partial TP before exit
        partial_before = ef_df[ef_df['partial_tp_before'] == True]
        print(f"\n--- PARTIAL TP BEFORE EXIT_FLAT ---")
        print(f"  Had partial TP: {len(partial_before)} ({len(partial_before)/len(ef_df)*100:.0f}%)")
        print(f"  No partial TP: {len(ef_df) - len(partial_before)} ({(len(ef_df)-len(partial_before))/len(ef_df)*100:.0f}%)")

        # Worst 20
        print(f"\n--- WORST 20 EXIT_FLAT TRADES ---")
        print(f"{'Date':<12} {'Entry':<8} {'Exit':<8} {'Dir':<6} {'PL':>7} {'MFE':>5} {'MAE':>6} {'Bars':>5} {'Type':<12} {'Bucket':<12}")
        for _, r in ef_df_sorted.head(20).iterrows():
            print(f"{r['date']:<12} {r['entry_time']:<8} {r['exit_time']:<8} {r['direction']:<6} "
                  f"{r['realized_pl']:>+7.0f} {r['max_favorable_excursion']:>5.0f} {r['max_adverse_excursion']:>6.0f} "
                  f"{r['bars_held']:>5} {r['entry_type']:<12} {r['time_bucket']:<12}")

    # === OPPORTUNITY WINDOW ANALYSIS ===
    print("\n\n" + "=" * 80)
    print("OPPORTUNITY WINDOW ANALYSIS")
    print("=" * 80)

    tw_df = pd.DataFrame(all_trades_with_windows)
    tw_df.to_csv('pinball_opportunity_windows.csv', index=False)

    # Only trades with realized P/L (exits, not entries)
    exits = tw_df[tw_df['realized_pl'] != 0.0].copy()

    print(f"\n{'Window':<14} {'Total PL':>9} {'Avg PL':>7} {'Win%':>6} {'Trades':>7} {'EF':>4} {'CTP':>4} {'PTP':>4} {'SE':>4} {'DayType':>8}")
    print("-" * 90)

    window_stats = []
    for bucket in sorted(exits['time_bucket'].unique()):
        subset = exits[exits['time_bucket'] == bucket]
        total_pl = subset['realized_pl'].sum()
        avg_pl = subset['realized_pl'].mean()
        win_pct = (subset['realized_pl'] > 0).sum() / len(subset) * 100 if len(subset) > 0 else 0
        ef_count = (subset['trade_type'] == 'EXIT_FLAT').sum()
        ctp_count = (subset['trade_type'] == 'CHOP_TP').sum()
        ptp_count = (subset['trade_type'] == 'PARTIAL_TP').sum()
        se_count = (subset['trade_type'] == 'SESSION_EXIT').sum()
        trend_pct = (subset['day_type'] == 'TREND').sum() / len(subset) * 100 if len(subset) > 0 else 0

        window_stats.append({
            'window': bucket, 'total_pl': total_pl, 'avg_pl': avg_pl,
            'win_pct': win_pct, 'trades': len(subset), 'ef': ef_count,
            'ctp': ctp_count, 'ptp': ptp_count, 'se': se_count,
        })

        print(f"{bucket:<14} {total_pl:>+9.0f} {avg_pl:>+7.1f} {win_pct:>5.1f}% {len(subset):>7} "
              f"{ef_count:>4} {ctp_count:>4} {ptp_count:>4} {se_count:>4} {trend_pct:>7.0f}%T")

    # Rank
    ws_df = pd.DataFrame(window_stats).sort_values('total_pl', ascending=False)
    print(f"\n--- RANKED BEST → WORST ---")
    for _, r in ws_df.iterrows():
        print(f"  {r['window']}: {r['total_pl']:>+8.0f} pts ({r['trades']} trades, {r['win_pct']:.0f}% win)")

    # Answers
    print(f"\n--- ANSWERS ---")
    best3 = ws_df.head(3)['window'].tolist()
    worst3 = ws_df.tail(3)['window'].tolist()
    print(f"1. Best windows: {best3}")
    print(f"2. Worst windows: {worst3}")
    dead_zones = ws_df[(ws_df['trades'] < 10) | (ws_df['total_pl'].abs() < 100)]
    print(f"3. Dead zones (low activity or near-zero P/L): {dead_zones['window'].tolist()}")

    # Would extending help?
    pre_1030 = ws_df[ws_df['window'].str[:5] <= '10:30']
    post_1030 = ws_df[ws_df['window'].str[:5] > '10:30']
    print(f"4. Pre-10:30 total: {pre_1030['total_pl'].sum():+.0f} | Post-10:30 total: {post_1030['total_pl'].sum():+.0f}")

    print(f"\n5. Suggested session schedules:")
    print(f"   A) {best3[0]} only (highest single window)")
    print(f"   B) {best3[0]} + {best3[1]} (top 2 combined)")
    print(f"   C) 09:30-10:30 (current default)")

    print(f"\nCSVs written: pinball_exit_flat_forensics.csv, pinball_opportunity_windows.csv")


if __name__ == "__main__":
    main()
