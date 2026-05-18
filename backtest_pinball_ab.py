"""
backtest_pinball_ab.py — A/B: Experiment v2 vs Pinball engine

6-day validation first, then full 682-day.
"""
import os, time, csv
import pandas as pd, pytz, numpy as np
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast
from belief_engine_experiment import BeliefEngineExperiment, BeliefConfig
from belief_engine_pinball import PinballEngine, PinballConfig

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

    # Experiment v2
    try:
        exp = BeliefEngineExperiment(BeliefConfig())
        exp.run_session(algo_df)
        exp_pl = exp.session_pl
        exp_trades = len(exp.trades)
    except Exception:
        exp_pl = 0.0; exp_trades = 0

    # Pinball
    try:
        pin = PinballEngine(PinballConfig())
        pin.run_session(algo_df)
        pin_pl = pin.session_pl
        pin_trades = len(pin.trades)
        pin_mode = pin.mode
    except Exception:
        pin_pl = 0.0; pin_trades = 0; pin_mode = "ERROR"

    return {
        'date': target_date, 'exp_pl': exp_pl, 'pin_pl': pin_pl,
        'exp_trades': exp_trades, 'pin_trades': pin_trades, 'pin_mode': pin_mode,
    }

def run_test(max_days=0, dates=None):
    if dates:
        files = [f'CBOT_MINI_YM1_{d}.csv' for d in dates]
    else:
        files = sorted([f for f in os.listdir(_DATA_ROOT)
                        if f.startswith('CBOT_MINI_YM1_') and f.endswith('.csv')])
        if max_days > 0: files = files[-max_days:]

    total = len(files)
    results = []
    t0 = time.time()
    for i, fname in enumerate(files):
        r = _run_day(fname)
        if r: results.append(r)
        if (i+1) % 100 == 0:
            print(f"  [{i+1}/{total}] {len(results)} valid, {time.time()-t0:.0f}s")

    n = len(results)
    if n == 0:
        print("No valid results."); return

    exp_total = sum(r['exp_pl'] for r in results)
    pin_total = sum(r['pin_pl'] for r in results)
    exp_wins = sum(1 for r in results if r['exp_pl'] > 0)
    pin_wins = sum(1 for r in results if r['pin_pl'] > 0)

    print(f"\n{'='*80}")
    print(f"{'METRIC':<25} {'EXPERIMENT':>12} {'PINBALL':>12} {'DELTA':>10}")
    print(f"{'-'*80}")
    print(f"{'Days':<25} {n:>12} {n:>12}")
    print(f"{'Total Pts':<25} {exp_total:>+12.0f} {pin_total:>+12.0f} {pin_total-exp_total:>+10.0f}")
    print(f"{'Avg/Day':<25} {exp_total/n:>+12.1f} {pin_total/n:>+12.1f} {(pin_total-exp_total)/n:>+10.1f}")
    print(f"{'Win Days':<25} {exp_wins:>12} {pin_wins:>12} {pin_wins-exp_wins:>+10}")
    print(f"{'Win %':<25} {exp_wins/n*100:>11.1f}% {pin_wins/n*100:>11.1f}%")
    exp_tpd = sum(r['exp_trades'] for r in results) / n
    pin_tpd = sum(r['pin_trades'] for r in results) / n
    print(f"{'Avg Trades/Day':<25} {exp_tpd:>12.1f} {pin_tpd:>12.1f}")
    print(f"{'='*80}")

    # Top/bottom
    sorted_pin = sorted(results, key=lambda r: r['pin_pl'])
    print(f"\nTOP 5 PINBALL LOSING DAYS:")
    for r in sorted_pin[:5]:
        print(f"  {r['date']}: pin={r['pin_pl']:+.0f} exp={r['exp_pl']:+.0f} mode={r['pin_mode']} trades={r['pin_trades']}")
    print(f"\nTOP 5 PINBALL WINNING DAYS:")
    for r in sorted_pin[-5:]:
        print(f"  {r['date']}: pin={r['pin_pl']:+.0f} exp={r['exp_pl']:+.0f} mode={r['pin_mode']} trades={r['pin_trades']}")

    # CSV
    with open('pinball_ab_results.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['date','exp_pl','pin_pl','exp_trades','pin_trades','pin_mode'])
        w.writeheader(); w.writerows(results)
    print(f"\nCSV: pinball_ab_results.csv ({n} rows)")

if __name__ == "__main__":
    import sys
    if "--6day" in sys.argv:
        dates = ['2026-02-05','2026-02-11','2026-02-13','2026-02-17','2025-04-21','2025-04-23']
        print("6-DAY VALIDATION: Experiment vs Pinball")
        run_test(dates=dates)
    else:
        print("FULL 682-DAY A/B: Experiment vs Pinball")
        run_test()
