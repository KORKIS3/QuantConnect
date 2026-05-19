"""Pinball v6 test: QUICK_KILL (Rule A) — 6-day validation + full 565-day."""
import os, time
import pandas as pd, pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast
from belief_engine_pinball_v4 import PinballEngine as V4, PinballConfig as V4Config
from belief_engine_pinball_v6 import PinballEngine as V6, PinballConfig as V6Config

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
    v6 = V6(V6Config()); v6.run_session(algo_df)
    return {'date': target_date, 'v4_pl': v4.session_pl, 'v6_pl': v6.session_pl,
            'v4_trades': v4.trades, 'v6_trades': v6.trades}

def _type_totals(trades):
    t = {}
    for tr in trades:
        tt = tr.get('trade_type','')
        pl = tr.get('realized_pl', 0.0)
        if tt not in t: t[tt] = {'count':0,'pl':0.0}
        t[tt]['count'] += 1; t[tt]['pl'] += pl
    return t

# 6-day validation
print("=== 6-DAY VALIDATION ===")
val_dates = ['2026-02-05','2026-02-11','2026-02-13','2026-02-17','2025-04-21','2025-04-23']
for d in val_dates:
    r = _run_day(f'CBOT_MINI_YM1_{d}.csv')
    if r: print(f"  {d}: v4={r['v4_pl']:+.0f}  v6={r['v6_pl']:+.0f}  delta={r['v6_pl']-r['v4_pl']:+.0f}")

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
v6_total = sum(r['v6_pl'] for r in results)
v4_wins = sum(1 for r in results if r['v4_pl'] > 0)
v6_wins = sum(1 for r in results if r['v6_pl'] > 0)
v6_pls = sorted([r['v6_pl'] for r in results])

all_v6_trades = []
for r in results: all_v6_trades.extend(r['v6_trades'])
v6_types = _type_totals(all_v6_trades)

print(f"\n{'='*60}")
print(f"{'METRIC':<20} {'V4 (baseline)':>14} {'V6 (QUICK_KILL)':>16} {'DELTA':>10}")
print(f"{'-'*60}")
print(f"{'Total Pts':<20} {v4_total:>+14.0f} {v6_total:>+16.0f} {v6_total-v4_total:>+10.0f}")
print(f"{'Avg/Day':<20} {v4_total/n:>+14.1f} {v6_total/n:>+16.1f} {(v6_total-v4_total)/n:>+10.1f}")
print(f"{'Win %':<20} {v4_wins/n*100:>13.1f}% {v6_wins/n*100:>15.1f}%")
print(f"{'Worst Day':<20} {'':>14} {v6_pls[0]:>+16.0f}")
print(f"{'Median Day':<20} {'':>14} {v6_pls[n//2]:>+16.0f}")
v4_trade_count = sum(len(r['v4_trades']) for r in results)
print(f"{'Total Trades':<20} {v4_trade_count:>14} {len(all_v6_trades):>16}")

print(f"\n--- V6 TRADE TYPE BREAKDOWN ---")
for tt in sorted(v6_types.keys()):
    s = v6_types[tt]
    if s['pl'] != 0 or tt == 'QUICK_KILL':
        print(f"  {tt:<20} {s['count']:>5} trades  {s['pl']:>+10.0f} pts  avg={s['pl']/max(s['count'],1):>+.1f}")

# Protected component check
chop_tp = v6_types.get('CHOP_TP', {}).get('pl', 0)
partial_tp = v6_types.get('PARTIAL_TP', {}).get('pl', 0)
qk = v6_types.get('QUICK_KILL', {}).get('pl', 0)
qk_count = v6_types.get('QUICK_KILL', {}).get('count', 0)
ef = v6_types.get('EXIT_FLAT', {}).get('pl', 0)
ef_count = v6_types.get('EXIT_FLAT', {}).get('count', 0)

print(f"\n{'='*60}")
print(f"PROTECTED COMPONENT REGRESSION CHECK")
print(f"{'='*60}")
print(f"  CHOP_TP:     {chop_tp:>+10.0f}  (baseline: +77,928, threshold: +74,032)")
print(f"  PARTIAL_TP:  {partial_tp:>+10.0f}  (baseline: +60,388, threshold: +57,369)")
chop_ok = chop_tp >= 77928 * 0.95
partial_ok = partial_tp >= 60388 * 0.95
print(f"  CHOP_TP:     {'PASS' if chop_ok else '*** REGRESSION ***'}")
print(f"  PARTIAL_TP:  {'PASS' if partial_ok else '*** REGRESSION ***'}")

print(f"\n--- QUICK_KILL IMPACT ---")
print(f"  QUICK_KILL trades: {qk_count}")
print(f"  QUICK_KILL total P/L: {qk:>+.0f}")
print(f"  QUICK_KILL avg P/L: {qk/max(qk_count,1):>+.1f}")
print(f"  EXIT_FLAT trades: {ef_count} (total: {ef:>+.0f})")
print(f"  Combined loss exits: {qk + ef:>+.0f}")

# Compare to v4 EXIT_FLAT
v4_types = _type_totals([t for r in results for t in r['v4_trades']])
v4_ef = v4_types.get('EXIT_FLAT', {}).get('pl', 0)
print(f"  V4 EXIT_FLAT was: {v4_ef:>+.0f}")
print(f"  Improvement: {(qk + ef) - v4_ef:>+.0f} pts")
