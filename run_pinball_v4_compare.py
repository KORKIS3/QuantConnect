"""Compare Pinball v3 vs v4 on full 565 days + opportunity window analysis."""
import os, time
import pandas as pd, pytz, numpy as np
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast
from belief_engine_pinball import PinballEngine, PinballConfig
from belief_engine_pinball_v4 import PinballEngine as PinballV4, PinballConfig as PinballConfigV4

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.join(os.path.expanduser("~"), "Desktop", "2YearsData", "full_day")

def _get_config():
    return AlgoConfig(warmup_minutes=7, steep_angle_threshold=90.0, proximity_points=4.0,
        min_reversal_minutes=0, min_entry_angle=0.0, partial_tp_pts=50.0,
        wm_shield_distance=0.0, swing_anchor_threshold=10.0)

def _time_bucket(time_str):
    h, m = int(time_str[:2]), int(time_str[3:5])
    total_min = h * 60 + m
    bucket_start = 9 * 60 + 30
    bucket_idx = (total_min - bucket_start) // 30
    bucket_h = (bucket_start + bucket_idx * 30) // 60
    bucket_m = (bucket_start + bucket_idx * 30) % 60
    end_h = (bucket_start + (bucket_idx + 1) * 30) // 60
    end_m = (bucket_start + (bucket_idx + 1) * 30) % 60
    return f"{bucket_h:02d}:{bucket_m:02d}-{end_h:02d}:{end_m:02d}"

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

    # V3
    v3 = PinballEngine(PinballConfig())
    v3.run_session(algo_df)

    # V4
    v4 = PinballV4(PinballConfigV4())
    v4.run_session(algo_df)

    # Collect v4 trades with time buckets
    v4_trades = []
    for t in v4.trades:
        tt = t.get('time', '')
        if hasattr(tt, 'strftime'):
            ts = tt.strftime('%H:%M:%S')
        else:
            ts = str(tt)
        v4_trades.append({
            'date': target_date,
            'time': ts,
            'time_bucket': _time_bucket(ts) if len(ts) >= 5 else 'UNKNOWN',
            'trade_type': t.get('trade_type', ''),
            'realized_pl': t.get('realized_pl', 0.0),
            'day_type': t.get('day_type', ''),
        })

    return {
        'date': target_date,
        'v3_pl': v3.session_pl,
        'v4_pl': v4.session_pl,
        'v3_trades': len(v3.trades),
        'v4_trades': len(v4.trades),
        'v4_trade_details': v4_trades,
    }

def main():
    files = sorted([f for f in os.listdir(_DATA_ROOT) if f.startswith('CBOT_MINI_YM1_') and f.endswith('.csv')])
    print(f"Running v3 vs v4 comparison on {len(files)} files...")

    results = []
    all_v4_trades = []
    t0 = time.time()

    for i, fname in enumerate(files):
        r = _run_day(fname)
        if r:
            results.append(r)
            all_v4_trades.extend(r['v4_trade_details'])
        if (i+1) % 100 == 0:
            print(f"  [{i+1}/{len(files)}] {len(results)} valid, {time.time()-t0:.0f}s")

    n = len(results)
    print(f"\nCompleted: {n} days in {time.time()-t0:.1f}s")

    # === COMPARISON ===
    v3_total = sum(r['v3_pl'] for r in results)
    v4_total = sum(r['v4_pl'] for r in results)
    v3_wins = sum(1 for r in results if r['v3_pl'] > 0)
    v4_wins = sum(1 for r in results if r['v4_pl'] > 0)
    v3_pls = sorted([r['v3_pl'] for r in results])
    v4_pls = sorted([r['v4_pl'] for r in results])

    print(f"\n{'='*70}")
    print(f"{'METRIC':<25} {'PINBALL v3':>12} {'PINBALL v4':>12} {'DELTA':>10}")
    print(f"{'-'*70}")
    print(f"{'Total Pts':<25} {v3_total:>+12.0f} {v4_total:>+12.0f} {v4_total-v3_total:>+10.0f}")
    print(f"{'Avg/Day':<25} {v3_total/n:>+12.1f} {v4_total/n:>+12.1f} {(v4_total-v3_total)/n:>+10.1f}")
    print(f"{'Win %':<25} {v3_wins/n*100:>11.1f}% {v4_wins/n*100:>11.1f}%")
    print(f"{'Median Day':<25} {v3_pls[n//2]:>+12.0f} {v4_pls[n//2]:>+12.0f}")
    print(f"{'Worst Day':<25} {v3_pls[0]:>+12.0f} {v4_pls[0]:>+12.0f}")
    print(f"{'Best Day':<25} {v3_pls[-1]:>+12.0f} {v4_pls[-1]:>+12.0f}")
    print(f"{'Total Trades':<25} {sum(r['v3_trades'] for r in results):>12} {sum(r['v4_trades'] for r in results):>12}")

    # Trade type breakdown for v4
    tw_df = pd.DataFrame(all_v4_trades)
    exits = tw_df[tw_df['realized_pl'] != 0.0]
    print(f"\n--- V4 TRADE TYPE BREAKDOWN ---")
    for tt in sorted(exits['trade_type'].unique()):
        subset = exits[exits['trade_type'] == tt]
        print(f"  {tt:<18} {len(subset):>5} trades  total={subset['realized_pl'].sum():>+8.0f}  avg={subset['realized_pl'].mean():>+6.1f}")

    # === OPPORTUNITY WINDOWS ===
    print(f"\n{'='*70}")
    print(f"V4 OPPORTUNITY WINDOW ANALYSIS")
    print(f"{'='*70}")
    print(f"{'Window':<14} {'Total PL':>9} {'Avg':>7} {'Win%':>6} {'Trades':>7} {'EHS':>4} {'EF':>4} {'CTP':>4} {'PTP':>4} {'SE':>4}")
    print("-" * 80)

    for bucket in sorted(exits['time_bucket'].unique()):
        s = exits[exits['time_bucket'] == bucket]
        total_pl = s['realized_pl'].sum()
        avg_pl = s['realized_pl'].mean()
        win_pct = (s['realized_pl'] > 0).sum() / len(s) * 100
        ehs = (s['trade_type'] == 'EARLY_HARD_STOP').sum()
        ef = (s['trade_type'] == 'EXIT_FLAT').sum()
        ctp = (s['trade_type'] == 'CHOP_TP').sum()
        ptp = (s['trade_type'] == 'PARTIAL_TP').sum()
        se = (s['trade_type'] == 'SESSION_EXIT').sum()
        print(f"{bucket:<14} {total_pl:>+9.0f} {avg_pl:>+7.1f} {win_pct:>5.1f}% {len(s):>7} {ehs:>4} {ef:>4} {ctp:>4} {ptp:>4} {se:>4}")

    # Rank
    window_pls = exits.groupby('time_bucket')['realized_pl'].sum().sort_values(ascending=False)
    print(f"\n--- RANKED BEST to WORST ---")
    for bucket, pl in window_pls.items():
        cnt = len(exits[exits['time_bucket'] == bucket])
        print(f"  {bucket}: {pl:>+8.0f} pts ({cnt} trades)")

    # Answers
    pre_1030 = exits[exits['time_bucket'].str[:5] <= '10:30']['realized_pl'].sum()
    post_1030 = exits[exits['time_bucket'].str[:5] > '10:30']['realized_pl'].sum()
    print(f"\nPre-10:30: {pre_1030:>+.0f} | Post-10:30: {post_1030:>+.0f}")
    print(f"{'='*70}")

if __name__ == "__main__":
    main()
