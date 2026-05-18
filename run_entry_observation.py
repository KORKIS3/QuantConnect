"""
run_entry_observation.py — ENTRY OBSERVATION forensic study

Hypothesis: The first 1-5 bars after entry reveal whether a trade is real.
Track bar-by-bar metrics for every entry and compare WINNERS vs LOSERS.
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


def _run_day(fname):
    target_date = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
    fpath = os.path.join(_DATA_ROOT, fname)
    try:
        df = pd.read_csv(fpath, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
    except Exception:
        return None
    if len(df) < 10: return None
    day_start = pd.Timestamp(f'{target_date} 09:30', tz=_EST)
    day_end = pd.Timestamp(f'{target_date} 16:59', tz=_EST)
    day_data = df[(df.index >= day_start) & (df.index <= day_end)]
    if len(day_data) < 15: return None
    if (day_data[["Open","High","Low","Close"]] <= 0).any().any(): return None
    if day_data["High"].max() == day_data["Low"].min(): return None
    if day_data["Volume"].sum() < 100: return None

    config = _get_config()
    try:
        algo_df = run_trading_algo_fast(day_data, target_date, '09:30', '17:00', config=config)
    except Exception:
        return None
    if algo_df is None or len(algo_df) < 15: return None

    engine = PinballV4(PinballConfigV4())
    engine.run_session(algo_df)
    return {'date': target_date, 'engine': engine, 'algo_df': algo_df, 'bar_logs': engine.bar_logs, 'trades': engine.trades}


def main():
    files = sorted([f for f in os.listdir(_DATA_ROOT) if f.startswith('CBOT_MINI_YM1_') and f.endswith('.csv')])
    print(f"Running ENTRY OBSERVATION on {len(files)} files...")

    all_entries = []
    t_start = time.time()
    valid_days = 0

    for i, fname in enumerate(files):
        result = _run_day(fname)
        if result is None: continue
        valid_days += 1

        bar_logs = result['bar_logs']
        trades = result['trades']
        algo_df = result['algo_df']
        target_date = result['date']

        # Pair entries with exits
        open_entry = None
        for t in trades:
            tt = t.get('trade_type', '')
            if tt in ('TREND_LONG', 'TREND_SHORT', 'CHOP_BUY', 'CHOP_SELL'):
                open_entry = {
                    'entry_type': tt,
                    'entry_price': t.get('exit_price', 0),
                    'direction': t.get('direction', ''),
                    'entry_time': t.get('time', ''),
                }
                # Find entry bar_idx
                entry_time_str = t['time'].strftime('%H:%M:%S') if hasattr(t['time'], 'strftime') else str(t['time'])
                entry_bar_idx = None
                for bl in bar_logs:
                    bl_t = bl['time'].strftime('%H:%M:%S') if hasattr(bl['time'], 'strftime') else ''
                    if bl_t == entry_time_str:
                        entry_bar_idx = bl['bar_idx']
                        break
                open_entry['bar_idx'] = entry_bar_idx
                continue

            # Exit found
            if open_entry and tt in ('EXIT_FLAT', 'EARLY_HARD_STOP', 'CHOP_TP', 'PARTIAL_TP', 'SESSION_EXIT', 'SPIKE_EXIT', 'CHOP_STOP'):
                exit_pl = t.get('realized_pl', 0.0)
                bars_held = t.get('bars_held', 0)
                outcome = "WINNER" if exit_pl > 0 else "LOSER"
                entry_bar_idx = open_entry.get('bar_idx')
                entry_price = open_entry['entry_price']
                direction = open_entry['direction']

                if entry_bar_idx is None or entry_bar_idx + 5 >= len(algo_df):
                    open_entry = None
                    continue

                # Collect bar 1-5 metrics
                bar_metrics = []
                running_mfe = 0.0
                running_mae = 0.0
                for offset in range(1, 6):
                    idx = entry_bar_idx + offset
                    if idx >= len(algo_df):
                        break
                    row = algo_df.iloc[idx]
                    close = float(row['Close'])
                    high = float(row['High'])
                    low = float(row['Low'])

                    if direction == 'long':
                        unrealized = close - entry_price
                        bar_mfe = high - entry_price
                        bar_mae = low - entry_price
                    else:
                        unrealized = entry_price - close
                        bar_mfe = entry_price - low
                        bar_mae = entry_price - high

                    running_mfe = max(running_mfe, bar_mfe)
                    running_mae = min(running_mae, bar_mae)

                    # Velocity: close change from previous bar
                    if idx > 0:
                        prev_close = float(algo_df.iloc[idx-1]['Close'])
                        velocity = close - prev_close if direction == 'long' else prev_close - close
                    else:
                        velocity = 0.0

                    bar_metrics.append({
                        'bar_offset': offset,
                        'unrealized': unrealized,
                        'mfe_cumulative': running_mfe,
                        'mae_cumulative': running_mae,
                        'velocity': velocity,
                        'bar_range': high - low,
                    })

                # Store entry record with bar 1-5 data
                entry_record = {
                    'date': target_date,
                    'entry_type': open_entry['entry_type'],
                    'exit_type': tt,
                    'direction': direction,
                    'outcome': outcome,
                    'realized_pl': exit_pl,
                    'bars_held': bars_held,
                    'entry_price': entry_price,
                }
                for bm in bar_metrics:
                    off = bm['bar_offset']
                    entry_record[f'bar{off}_unrealized'] = bm['unrealized']
                    entry_record[f'bar{off}_mfe'] = bm['mfe_cumulative']
                    entry_record[f'bar{off}_mae'] = bm['mae_cumulative']
                    entry_record[f'bar{off}_velocity'] = bm['velocity']
                    entry_record[f'bar{off}_range'] = bm['bar_range']

                all_entries.append(entry_record)
                open_entry = None

        if (i+1) % 100 == 0:
            print(f"  [{i+1}/{len(files)}] {valid_days} valid, {len(all_entries)} entries, {time.time()-t_start:.0f}s")

    elapsed = time.time() - t_start
    n = len(all_entries)
    print(f"\nCompleted: {valid_days} days, {n} entries in {elapsed:.1f}s")

    df = pd.DataFrame(all_entries)
    df.to_csv('entry_observation_forensics.csv', index=False)

    winners = df[df['outcome'] == 'WINNER']
    losers = df[df['outcome'] == 'LOSER']

    print(f"\n{'='*80}")
    print(f"ENTRY OBSERVATION RESULTS")
    print(f"{'='*80}")
    print(f"Total entries: {n}")
    print(f"  Winners: {len(winners)} ({len(winners)/n*100:.0f}%) avg P/L: {winners['realized_pl'].mean():+.1f}")
    print(f"  Losers: {len(losers)} ({len(losers)/n*100:.0f}%) avg P/L: {losers['realized_pl'].mean():+.1f}")

    # Bar-by-bar comparison
    print(f"\n--- BAR-BY-BAR COMPARISON (avg values) ---")
    print(f"{'Bar':<5} {'W_Unreal':>9} {'L_Unreal':>9} {'W_MFE':>7} {'L_MFE':>7} {'W_MAE':>7} {'L_MAE':>7} {'W_Vel':>7} {'L_Vel':>7}")
    print("-" * 75)
    for off in range(1, 6):
        w_ur = winners[f'bar{off}_unrealized'].mean()
        l_ur = losers[f'bar{off}_unrealized'].mean()
        w_mfe = winners[f'bar{off}_mfe'].mean()
        l_mfe = losers[f'bar{off}_mfe'].mean()
        w_mae = winners[f'bar{off}_mae'].mean()
        l_mae = losers[f'bar{off}_mae'].mean()
        w_vel = winners[f'bar{off}_velocity'].mean()
        l_vel = losers[f'bar{off}_velocity'].mean()
        print(f"  {off:<3} {w_ur:>+9.1f} {l_ur:>+9.1f} {w_mfe:>+7.1f} {l_mfe:>+7.1f} {w_mae:>+7.1f} {l_mae:>+7.1f} {w_vel:>+7.1f} {l_vel:>+7.1f}")

    # Separation analysis
    print(f"\n--- SEPARATION ANALYSIS ---")
    for off in range(1, 6):
        w_ur = winners[f'bar{off}_unrealized'].mean()
        l_ur = losers[f'bar{off}_unrealized'].mean()
        separation = w_ur - l_ur
        print(f"  Bar {off}: Winner avg={w_ur:+.1f}, Loser avg={l_ur:+.1f}, Separation={separation:+.1f} pts")

    # Classification at bar 3
    print(f"\n--- BAR 3 CLASSIFICATION ---")
    # Immediately wrong: MFE < 5 and unrealized < -20 at bar 3
    immediately_wrong = df[(df['bar3_mfe'] < 5) & (df['bar3_unrealized'] < -20)]
    # Healthy: unrealized > 0 at bar 3
    healthy = df[df['bar3_unrealized'] > 0]
    # Uncertain: everything else
    uncertain = df[~df.index.isin(immediately_wrong.index) & ~df.index.isin(healthy.index)]

    print(f"  Immediately wrong (MFE<5, unreal<-20 at bar 3): {len(immediately_wrong)} ({len(immediately_wrong)/n*100:.0f}%)")
    print(f"    Avg final P/L: {immediately_wrong['realized_pl'].mean():+.1f}")
    print(f"    Win rate: {(immediately_wrong['realized_pl'] > 0).sum()}/{len(immediately_wrong)} ({(immediately_wrong['realized_pl'] > 0).sum()/max(len(immediately_wrong),1)*100:.0f}%)")
    print(f"  Healthy (unrealized > 0 at bar 3): {len(healthy)} ({len(healthy)/n*100:.0f}%)")
    print(f"    Avg final P/L: {healthy['realized_pl'].mean():+.1f}")
    print(f"    Win rate: {(healthy['realized_pl'] > 0).sum()}/{len(healthy)} ({(healthy['realized_pl'] > 0).sum()/max(len(healthy),1)*100:.0f}%)")
    print(f"  Uncertain: {len(uncertain)} ({len(uncertain)/n*100:.0f}%)")
    print(f"    Avg final P/L: {uncertain['realized_pl'].mean():+.1f}")
    print(f"    Win rate: {(uncertain['realized_pl'] > 0).sum()}/{len(uncertain)} ({(uncertain['realized_pl'] > 0).sum()/max(len(uncertain),1)*100:.0f}%)")

    # === SIMULATIONS ===
    print(f"\n{'='*80}")
    print(f"SIMULATIONS")
    print(f"{'='*80}")

    # Current total P/L
    current_total = df['realized_pl'].sum()
    print(f"Current total P/L from all entries: {current_total:+.0f}")

    # Rule A: if MFE < 5 and unrealized < -20 after 3 bars → EXIT at bar 3 price
    print(f"\n--- RULE A: Exit if MFE<5 and unrealized<-20 at bar 3 ---")
    rule_a_targets = df[(df['bar3_mfe'] < 5) & (df['bar3_unrealized'] < -20)].copy()
    # These would exit at bar 3 unrealized instead of their actual realized_pl
    rule_a_saved = rule_a_targets['realized_pl'].sum() - rule_a_targets['bar3_unrealized'].sum()
    rule_a_new_total = current_total - rule_a_targets['realized_pl'].sum() + rule_a_targets['bar3_unrealized'].sum()
    print(f"  Trades affected: {len(rule_a_targets)}")
    print(f"  Current P/L of those trades: {rule_a_targets['realized_pl'].sum():+.0f}")
    print(f"  Would exit at bar 3 P/L: {rule_a_targets['bar3_unrealized'].sum():+.0f}")
    print(f"  Points saved: {-rule_a_saved:+.0f}")
    print(f"  New total P/L: {rule_a_new_total:+.0f} (was {current_total:+.0f})")
    print(f"  New avg/day: {rule_a_new_total/565:+.1f} (was {current_total/565:+.1f})")

    # Rule B: if trade reaches +20 within first 3 bars → trailing stop (assume captures 50% of MFE)
    print(f"\n--- RULE B: Trailing stop if +20 within 3 bars ---")
    rule_b_targets = df[df['bar3_mfe'] >= 20].copy()
    # Estimate: trailing stop captures ~60% of eventual MFE for winners, limits giveback for losers
    rule_b_losers = rule_b_targets[rule_b_targets['outcome'] == 'LOSER']
    # Losers with MFE>20 at bar 3 would be saved: instead of realized_pl, they'd exit at ~+10 (trailing from +20)
    rule_b_saved_from_losers = rule_b_losers['realized_pl'].sum() - len(rule_b_losers) * 10  # assume exit at +10
    print(f"  Trades reaching +20 by bar 3: {len(rule_b_targets)}")
    print(f"  Of those, eventual losers: {len(rule_b_losers)}")
    print(f"  Loser P/L currently: {rule_b_losers['realized_pl'].sum():+.0f}")
    print(f"  If trailing stop saved them at +10: {len(rule_b_losers) * 10:+.0f}")
    print(f"  Points saved from losers: {-rule_b_saved_from_losers:+.0f}")

    # Rule C: if no progress after 5 bars (unrealized between -10 and +10) → EXIT_FLAT
    print(f"\n--- RULE C: Exit if no progress after 5 bars (|unrealized| < 10) ---")
    rule_c_targets = df[(df['bar5_unrealized'].abs() < 10)].copy()
    rule_c_current = rule_c_targets['realized_pl'].sum()
    # Would exit at ~0 instead
    rule_c_new = 0  # exit at breakeven
    print(f"  Trades with no progress at bar 5: {len(rule_c_targets)} ({len(rule_c_targets)/n*100:.0f}%)")
    print(f"  Current P/L of those trades: {rule_c_current:+.0f}")
    print(f"  If exited at bar 5 (~breakeven): +0")
    print(f"  Points saved: {-rule_c_current:+.0f}")
    print(f"  New total: {current_total - rule_c_current:+.0f}")
    print(f"  New avg/day: {(current_total - rule_c_current)/565:+.1f}")

    # Combined simulation
    print(f"\n--- COMBINED (A + B + C, non-overlapping) ---")
    # Apply A first, then B on remainder, then C on remainder
    a_idx = set(rule_a_targets.index)
    b_idx = set(rule_b_targets.index) - a_idx
    c_idx = set(rule_c_targets.index) - a_idx - b_idx

    combined_saved = 0
    # A: exit at bar 3 unrealized
    a_current = df.loc[list(a_idx), 'realized_pl'].sum()
    a_new = df.loc[list(a_idx), 'bar3_unrealized'].sum()
    combined_saved += (a_current - a_new)

    # B: losers with MFE>20 exit at +10
    b_losers_idx = [idx for idx in b_idx if df.loc[idx, 'outcome'] == 'LOSER']
    b_current = df.loc[b_losers_idx, 'realized_pl'].sum() if b_losers_idx else 0
    b_new = len(b_losers_idx) * 10
    combined_saved += (b_current - b_new)

    # C: no progress exits at 0
    c_current = df.loc[list(c_idx), 'realized_pl'].sum() if c_idx else 0
    combined_saved += c_current  # saving = removing the loss

    combined_new_total = current_total - combined_saved
    print(f"  Rule A affects: {len(a_idx)} trades")
    print(f"  Rule B affects: {len(b_losers_idx)} loser trades")
    print(f"  Rule C affects: {len(c_idx)} trades")
    print(f"  Total points impact: {-combined_saved:+.0f}")
    print(f"  New total P/L: {combined_new_total:+.0f} (was {current_total:+.0f})")
    print(f"  New avg/day: {combined_new_total/565:+.1f} (was {current_total/565:+.1f})")

    # Protected component check
    print(f"\n--- PROTECTED COMPONENT CHECK ---")
    chop_tp = df[df['exit_type'] == 'CHOP_TP']['realized_pl'].sum()
    partial_tp = df[df['exit_type'] == 'PARTIAL_TP']['realized_pl'].sum()
    print(f"  CHOP_TP total: {chop_tp:+.0f} (baseline: +77,928)")
    print(f"  PARTIAL_TP total: {partial_tp:+.0f} (baseline: +60,388)")
    print(f"  Note: These rules only affect EXIT_FLAT/EARLY_HARD_STOP trades, not CHOP_TP/PARTIAL_TP")

    print(f"\nCSV: entry_observation_forensics.csv ({n} rows)")


if __name__ == "__main__":
    main()
