"""Pinball v5 test: 6-day validation then full 565-day."""
import os, time
import pandas as pd, pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast
from belief_engine_pinball_v4 import PinballEngine as V4, PinballConfig as V4Config
from belief_engine_pinball_v5 import PinballEngine as V5, PinballConfig as V5Config

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
    except: return None
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
    except: return None
    if algo_df is None or len(algo_df) < 15: return None

    v4 = V4(V4Config()); v4.run_session(algo_df)
    v5 = V5(V5Config()); v5.run_session(algo_df)
    return {'date': target_date, 'v4_pl': v4.session_pl, 'v5_pl': v5.session_pl,
            'v4_trades': v4.trades, 'v5_trades': v5.trades}

def _trade_type_totals(trades):
    totals = {}
    for t in trades:
        tt = t.get('trade_type', '')
        pl = t.get('realized_pl', 0.0)
        if tt not in totals: totals[tt] = {'count': 0, 'pl': 0.0}
        totals[tt]['count'] += 1
        totals[tt]['pl'] += pl
    return totals

# 6-day validation
print("=== 6-DAY VALIDATION ===")
val_dates = ['2026-02-05','2026-02-11','2026-02-13','2026-02-17','2025-04-21','2025-04-23']
for d in val_dates:
    fname = f'CBOT_MINI_YM1_{d}.csv'
    r = _run_day(fname)
    if r:
        print(f"  {d}: v4={r['v4_pl']:+.0f}  v5={r['v5_pl']:+.0f}  delta={r['v5_pl']-r['v4_pl']:+.0f}")

# Full test
print("\n=== FULL 565-DAY TEST ===")
files = sorted([f for f in os.listdir(_DATA_ROOT) if f.startswith('CBOT_MINI_YM1_') and f.endswith('.csv')])
results = []; t0 = time.time()
for i, fname in enumerate(files):
    r = _run_day(fname)
    if r: results.append(r)
    if (i+1) % 100 == 0: print(f"  [{i+1}/{len(files)}] {len(results)} valid, {time.time()-t0:.0f}s")

n = len(results)
v4_total = sum(r['v4_pl'] for r in results)
v5_total = sum(r['v5_pl'] for r in results)
v4_wins = sum(1 for r in results if r['v4_pl'] > 0)
v5_wins = sum(1 for r in results if r['v5_pl'] > 0)

# Aggregate trade types for v5
all_v5_trades = []
for r in results: all_v5_trades.extend(r['v5_trades'])
v5_types = _trade_type_totals(all_v5_trades)

print(f"\n{'METRIC':<20} {'V4':>10} {'V5':>10} {'DELTA':>10}")
print("-" * 55)
print(f"{'Total Pts':<20} {v4_total:>+10.0f} {v5_total:>+10.0f} {v5_total-v4_total:>+10.0f}")
print(f"{'Avg/Day':<20} {v4_total/n:>+10.1f} {v5_total/n:>+10.1f} {(v5_total-v4_total)/n:>+10.1f}")
print(f"{'Win %':<20} {v4_wins/n*100:>9.1f}% {v5_wins/n*100:>9.1f}%")
print(f"{'Total Trades':<20} {sum(len(r['v4_trades']) for r in results):>10} {len(all_v5_trades):>10}")

print(f"\n--- V5 TRADE TYPE BREAKDOWN ---")
for tt in sorted(v5_types.keys()):
    s = v5_types[tt]
    print(f"  {tt:<20} {s['count']:>5} trades  {s['pl']:>+10.0f} pts")

# Protected component check
chop_tp = v5_types.get('CHOP_TP', {}).get('pl', 0)
partial_tp = v5_types.get('PARTIAL_TP', {}).get('pl', 0)
obs_trail = v5_types.get('OBS_TRAIL_EXIT', {}).get('pl', 0)
obs_trail_count = v5_types.get('OBS_TRAIL_EXIT', {}).get('count', 0)
obs_on_count = v5_types.get('OBS_TRAIL_ON', {}).get('count', 0)

print(f"\n--- PROTECTED COMPONENT CHECK ---")
print(f"  CHOP_TP:     {chop_tp:>+10.0f} (baseline: +77,928)")
print(f"  PARTIAL_TP:  {partial_tp:>+10.0f} (baseline: +60,388)")
chop_regression = chop_tp < 77928 * 0.95
partial_regression = partial_tp < 60388 * 0.95
if chop_regression: print(f"  *** REGRESSION: CHOP_TP below 95% of baseline ***")
if partial_regression: print(f"  *** REGRESSION: PARTIAL_TP below 95% of baseline ***")
if not chop_regression and not partial_regression: print(f"  PASS: No regression detected")

print(f"\n--- OBS TRAILING STOP IMPACT ---")
print(f"  OBS_TRAIL_ON activations: {obs_on_count}")
print(f"  OBS_TRAIL_EXIT trades: {obs_trail_count}")
print(f"  OBS_TRAIL_EXIT total P/L: {obs_trail:>+.0f}")
print(f"  OBS_TRAIL_EXIT avg P/L: {obs_trail/max(obs_trail_count,1):>+.1f}")
