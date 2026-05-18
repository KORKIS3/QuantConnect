"""
run_false_trend_forensics.py — FALSE TREND forensic study

Hypothesis: Pinball falsely classifies CHOP as TREND, leading to bad entries.
Compare TRUE TREND (profitable) vs FALSE TREND (entries that became EXIT_FLAT losses).

Captures structure, time, volatility, and behavior metrics for each TREND entry.
"""
import os, time
import numpy as np
import pandas as pd
import pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast
from belief_engine_pinball_v4 import PinballEngine as PinballV4, PinballConfig as PinballConfigV4

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")


def _get_config():
    return AlgoConfig(warmup_minutes=7, steep_angle_threshold=90.0, proximity_points=4.0,
        min_reversal_minutes=0, min_entry_angle=0.0, partial_tp_pts=50.0,
        wm_shield_distance=0.0, swing_anchor_threshold=10.0)


def _compute_atr(highs, lows, closes, period=14):
    """Simple ATR calculation."""
    n = len(highs)
    if n < 2:
        return 0.0
    trs = []
    for i in range(1, n):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        trs.append(tr)
    if len(trs) < period:
        return np.mean(trs) if trs else 0.0
    return np.mean(trs[-period:])


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

    engine = PinballV4(PinballConfigV4())
    engine.run_session(algo_df)

    return {
        'date': target_date,
        'engine': engine,
        'algo_df': algo_df,
        'day_data': day_data,
    }


def main():
    files = sorted([f for f in os.listdir(_DATA_ROOT)
                    if f.startswith('CBOT_MINI_YM1_') and f.endswith('.csv')])
    print(f"Running FALSE TREND forensics on {len(files)} files...")

    all_trend_entries = []
    t_start = time.time()
    valid_days = 0

    for i, fname in enumerate(files):
        result = _run_day(fname)
        if result is None:
            continue
        valid_days += 1

        engine = result['engine']
        algo_df = result['algo_df']
        bar_logs = engine.bar_logs
        trades = engine.trades
        target_date = result['date']

        # Extract TREND entries and their outcomes
        # Walk through trades to pair entries with exits
        open_entry = None
        for t in trades:
            tt = t.get('trade_type', '')
            trade_time = t.get('time', '')
            if hasattr(trade_time, 'strftime'):
                time_str = trade_time.strftime('%H:%M:%S')
            else:
                time_str = str(trade_time)

            # Track TREND entries
            if tt in ('TREND_LONG', 'TREND_SHORT'):
                open_entry = {
                    'entry_time': time_str,
                    'entry_type': tt,
                    'entry_price': t.get('exit_price', 0),
                    'direction': t.get('direction', ''),
                }
                continue

            # Track exits that close a TREND entry
            if open_entry and tt in ('EXIT_FLAT', 'EARLY_HARD_STOP', 'CHOP_TP', 'PARTIAL_TP', 'SESSION_EXIT', 'SPIKE_EXIT', 'CHOP_STOP'):
                exit_pl = t.get('realized_pl', 0.0)
                bars_held = t.get('bars_held', 0)
                exit_price = t.get('exit_price', 0)

                # Determine if this was a TRUE or FALSE trend entry
                # TRUE = profitable exit (CHOP_TP, PARTIAL_TP, SPIKE_EXIT, or SESSION_EXIT with profit)
                # FALSE = loss exit (EXIT_FLAT, EARLY_HARD_STOP, or SESSION_EXIT with loss)
                if tt in ('EXIT_FLAT', 'EARLY_HARD_STOP', 'CHOP_STOP'):
                    outcome = "FALSE_TREND"
                elif tt in ('CHOP_TP', 'PARTIAL_TP', 'SPIKE_EXIT'):
                    outcome = "TRUE_TREND"
                elif tt == 'SESSION_EXIT':
                    outcome = "TRUE_TREND" if exit_pl > 0 else "FALSE_TREND"
                else:
                    outcome = "UNKNOWN"

                # Compute structure metrics at entry time
                entry_bar_idx = None
                for bl in bar_logs:
                    bl_time = bl['time'].strftime('%H:%M:%S') if hasattr(bl['time'], 'strftime') else ''
                    if bl_time == open_entry['entry_time']:
                        entry_bar_idx = bl['bar_idx']
                        break

                # Get algo_df data at entry
                slope_purple = 0.0
                slope_blue = 0.0
                orange_val = 0.0
                yellow_val = 0.0
                purple_val = 0.0
                blue_val = 0.0
                if entry_bar_idx is not None and entry_bar_idx < len(algo_df):
                    row = algo_df.iloc[entry_bar_idx]
                    slope_purple = float(row.get('purple_slope', 0)) if 'purple_slope' in row.index else 0.0
                    slope_blue = float(row.get('blue_slope', 0)) if 'blue_slope' in row.index else 0.0
                    purple_val = float(row.get('purple_ray', 0)) if 'purple_ray' in row.index else 0.0
                    blue_val = float(row.get('blue_ray', 0)) if 'blue_ray' in row.index else 0.0
                    orange_val = float(row.get('orange_ray', 0)) if 'orange_ray' in row.index else 0.0
                    yellow_val = float(row.get('yellow_ray', 0)) if 'yellow_ray' in row.index else 0.0

                # Line spacing
                line_spacing = abs(purple_val - blue_val) if purple_val and blue_val else 0.0
                support_resistance_dist = abs(orange_val - yellow_val) if orange_val and yellow_val else 0.0

                # Volatility at entry
                if entry_bar_idx and entry_bar_idx >= 5:
                    recent_highs = algo_df['High'].iloc[max(0, entry_bar_idx-14):entry_bar_idx+1].values
                    recent_lows = algo_df['Low'].iloc[max(0, entry_bar_idx-14):entry_bar_idx+1].values
                    recent_closes = algo_df['Close'].iloc[max(0, entry_bar_idx-14):entry_bar_idx+1].values
                    atr = _compute_atr(recent_highs, recent_lows, recent_closes)
                    avg_bar_size = np.mean(recent_highs - recent_lows)
                    # Velocity: price change over last 5 bars
                    if entry_bar_idx >= 5:
                        velocity = algo_df['Close'].iloc[entry_bar_idx] - algo_df['Close'].iloc[entry_bar_idx - 5]
                    else:
                        velocity = 0.0
                    # New highs/lows in last 10 bars
                    window_h = algo_df['High'].iloc[max(0, entry_bar_idx-10):entry_bar_idx+1]
                    window_l = algo_df['Low'].iloc[max(0, entry_bar_idx-10):entry_bar_idx+1]
                    new_highs = sum(1 for j in range(1, len(window_h)) if window_h.iloc[j] > window_h.iloc[:j].max())
                    new_lows = sum(1 for j in range(1, len(window_l)) if window_l.iloc[j] < window_l.iloc[:j].min())
                else:
                    atr = 0.0; avg_bar_size = 0.0; velocity = 0.0; new_highs = 0; new_lows = 0

                # MFE/MAE from bar logs
                max_fav = 0.0; max_adv = 0.0
                entry_price = open_entry['entry_price']
                direction = open_entry['direction']
                if entry_bar_idx is not None:
                    for bl in bar_logs:
                        if entry_bar_idx <= bl['bar_idx'] <= entry_bar_idx + bars_held:
                            if direction == 'long':
                                move = bl['close'] - entry_price
                            else:
                                move = entry_price - bl['close']
                            if move > max_fav: max_fav = move
                            if move < max_adv: max_adv = move

                # Confidence at entry
                confidence_at_entry = 0.0
                for bl in bar_logs:
                    if bl.get('bar_idx') == entry_bar_idx:
                        confidence_at_entry = bl.get('confidence', 0.0)
                        break

                # Bars since open
                bars_since_open = entry_bar_idx if entry_bar_idx else 0

                all_trend_entries.append({
                    'date': target_date,
                    'outcome': outcome,
                    'entry_time': open_entry['entry_time'],
                    'exit_time': time_str,
                    'entry_type': open_entry['entry_type'],
                    'exit_type': tt,
                    'direction': direction,
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'realized_pl': exit_pl,
                    'bars_held': bars_held,
                    'bars_since_open': bars_since_open,
                    # Structure
                    'slope_purple': slope_purple,
                    'slope_blue': slope_blue,
                    'line_spacing': line_spacing,
                    'support_resistance_dist': support_resistance_dist,
                    'new_highs_10bar': new_highs,
                    'new_lows_10bar': new_lows,
                    # Volatility
                    'atr_14': atr,
                    'avg_bar_size': avg_bar_size,
                    'velocity_5bar': velocity,
                    # Behavior
                    'mfe': max_fav,
                    'mae': max_adv,
                    'confidence_at_entry': confidence_at_entry,
                    # Time
                    'entry_hour': int(open_entry['entry_time'][:2]) if len(open_entry['entry_time']) >= 2 else 0,
                })

                open_entry = None  # reset

        if (i + 1) % 100 == 0:
            print(f"  [{i+1}/{len(files)}] {valid_days} valid, {len(all_trend_entries)} trend entries, {time.time()-t_start:.0f}s")

    elapsed = time.time() - t_start
    print(f"\nCompleted: {valid_days} days, {len(all_trend_entries)} TREND entries in {elapsed:.1f}s")

    # === SAVE CSV ===
    df = pd.DataFrame(all_trend_entries)
    df.to_csv('false_trend_forensics.csv', index=False)

    # === ANALYSIS ===
    true_trends = df[df['outcome'] == 'TRUE_TREND']
    false_trends = df[df['outcome'] == 'FALSE_TREND']

    print(f"\n{'='*80}")
    print(f"FALSE TREND FORENSIC RESULTS")
    print(f"{'='*80}")
    print(f"Total TREND entries: {len(df)}")
    print(f"  TRUE TREND (profitable): {len(true_trends)} ({len(true_trends)/len(df)*100:.0f}%)")
    print(f"  FALSE TREND (loss): {len(false_trends)} ({len(false_trends)/len(df)*100:.0f}%)")
    print(f"  TRUE avg P/L: {true_trends['realized_pl'].mean():+.1f}")
    print(f"  FALSE avg P/L: {false_trends['realized_pl'].mean():+.1f}")

    # Compare metrics
    metrics = ['slope_purple', 'slope_blue', 'line_spacing', 'support_resistance_dist',
               'new_highs_10bar', 'new_lows_10bar', 'atr_14', 'avg_bar_size',
               'velocity_5bar', 'mfe', 'mae', 'bars_held', 'bars_since_open',
               'confidence_at_entry', 'entry_hour']

    print(f"\n{'METRIC':<25} {'TRUE_TREND':>12} {'FALSE_TREND':>12} {'DIFF':>10} {'SIGNAL':>8}")
    print("-" * 70)
    for m in metrics:
        if m not in df.columns:
            continue
        t_mean = true_trends[m].mean() if len(true_trends) > 0 else 0
        f_mean = false_trends[m].mean() if len(false_trends) > 0 else 0
        diff = t_mean - f_mean
        # Signal strength: how different are they?
        combined_std = df[m].std()
        signal = abs(diff) / combined_std if combined_std > 0 else 0
        signal_str = "***" if signal > 0.5 else "**" if signal > 0.3 else "*" if signal > 0.15 else ""
        print(f"  {m:<23} {t_mean:>12.2f} {f_mean:>12.2f} {diff:>+10.2f} {signal_str:>8}")

    # Time of day analysis
    print(f"\n--- BY ENTRY HOUR ---")
    print(f"{'Hour':<6} {'TRUE':>6} {'FALSE':>6} {'False%':>7}")
    for h in sorted(df['entry_hour'].unique()):
        t_count = len(true_trends[true_trends['entry_hour'] == h])
        f_count = len(false_trends[false_trends['entry_hour'] == h])
        total = t_count + f_count
        pct = f_count / total * 100 if total > 0 else 0
        print(f"  {h:>4}  {t_count:>6} {f_count:>6} {pct:>6.0f}%")

    # MFE analysis
    print(f"\n--- MFE DISTRIBUTION ---")
    print(f"  TRUE TREND avg MFE: {true_trends['mfe'].mean():+.1f}")
    print(f"  FALSE TREND avg MFE: {false_trends['mfe'].mean():+.1f}")
    print(f"  FALSE with MFE > 20 (had profit, lost it): {(false_trends['mfe'] > 20).sum()}")
    print(f"  FALSE with MFE < 5 (never profitable): {(false_trends['mfe'] < 5).sum()}")

    # Velocity analysis
    print(f"\n--- VELOCITY AT ENTRY ---")
    print(f"  TRUE TREND avg velocity: {true_trends['velocity_5bar'].mean():+.1f}")
    print(f"  FALSE TREND avg velocity: {false_trends['velocity_5bar'].mean():+.1f}")
    print(f"  TRUE abs velocity: {true_trends['velocity_5bar'].abs().mean():.1f}")
    print(f"  FALSE abs velocity: {false_trends['velocity_5bar'].abs().mean():.1f}")

    # Recommendations
    print(f"\n{'='*80}")
    print(f"RECOMMENDATIONS")
    print(f"{'='*80}")
    print(f"Based on the data, a stricter TREND detector should require:")

    # Find thresholds that separate true from false
    if len(true_trends) > 0 and len(false_trends) > 0:
        # Velocity
        true_vel = true_trends['velocity_5bar'].abs().mean()
        false_vel = false_trends['velocity_5bar'].abs().mean()
        print(f"  1. |velocity_5bar| >= {(true_vel + false_vel) / 2:.1f} (true={true_vel:.1f}, false={false_vel:.1f})")

        # New extremes
        true_ext = true_trends[['new_highs_10bar', 'new_lows_10bar']].max(axis=1).mean()
        false_ext = false_trends[['new_highs_10bar', 'new_lows_10bar']].max(axis=1).mean()
        print(f"  2. new_extremes_10bar >= {max(1, int((true_ext + false_ext) / 2))} (true={true_ext:.1f}, false={false_ext:.1f})")

        # ATR
        true_atr = true_trends['atr_14'].mean()
        false_atr = false_trends['atr_14'].mean()
        print(f"  3. ATR_14 >= {(true_atr + false_atr) / 2:.1f} (true={true_atr:.1f}, false={false_atr:.1f})")

        # Bars since open
        true_bso = true_trends['bars_since_open'].mean()
        false_bso = false_trends['bars_since_open'].mean()
        print(f"  4. bars_since_open >= {int((true_bso + false_bso) / 2)} (true={true_bso:.0f}, false={false_bso:.0f})")

        # Simulate stricter filter
        print(f"\n--- SIMULATION: Stricter TREND filter ---")
        vel_threshold = (true_vel + false_vel) / 2
        ext_threshold = max(1, int((true_ext + false_ext) / 2))

        would_pass_true = true_trends[
            (true_trends['velocity_5bar'].abs() >= vel_threshold) &
            (true_trends[['new_highs_10bar', 'new_lows_10bar']].max(axis=1) >= ext_threshold)
        ]
        would_pass_false = false_trends[
            (false_trends['velocity_5bar'].abs() >= vel_threshold) &
            (false_trends[['new_highs_10bar', 'new_lows_10bar']].max(axis=1) >= ext_threshold)
        ]
        print(f"  TRUE entries surviving filter: {len(would_pass_true)}/{len(true_trends)} ({len(would_pass_true)/len(true_trends)*100:.0f}%)")
        print(f"  FALSE entries eliminated: {len(false_trends) - len(would_pass_false)}/{len(false_trends)} ({(len(false_trends)-len(would_pass_false))/len(false_trends)*100:.0f}%)")
        print(f"  FALSE entries still passing: {len(would_pass_false)}/{len(false_trends)} ({len(would_pass_false)/len(false_trends)*100:.0f}%)")

        eliminated_loss = false_trends[
            ~((false_trends['velocity_5bar'].abs() >= vel_threshold) &
              (false_trends[['new_highs_10bar', 'new_lows_10bar']].max(axis=1) >= ext_threshold))
        ]['realized_pl'].sum()
        print(f"  P/L saved by eliminating false entries: {-eliminated_loss:+.0f} pts")

    print(f"\nCSV: false_trend_forensics.csv ({len(df)} rows)")


if __name__ == "__main__":
    main()
