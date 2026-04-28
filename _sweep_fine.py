import os, pytz, pandas as pd, time
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

_EST = pytz.timezone('US/Eastern')
_DATA_ROOT = os.path.join(os.path.expanduser('~'), 'Desktop', '2YearsData', 'full_day')
_CSV_FILES = sorted([f for f in os.listdir(_DATA_ROOT) if f.startswith('CBOT_MINI_YM1_') and f.endswith('.csv')])

BASE = dict(warmup_minutes=8, steep_angle_threshold=75.0, proximity_points=8.0,
            min_reversal_minutes=0, min_entry_angle=0.0, partial_tp_pts=50.0,
            wm_shield_distance=0.0, swing_anchor_threshold=25.0)

def run_config(**kwargs):
    cfg = AlgoConfig(**{**BASE, **kwargs})
    total_pl = 0.0; wins = 0; days = 0
    for fname in _CSV_FILES:
        date = fname.replace('CBOT_MINI_YM1_','').replace('.csv','')
        df = pd.read_csv(os.path.join(_DATA_ROOT, fname), index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        day = df[(df.index >= pd.Timestamp(date+' 09:30', tz=_EST)) & (df.index <= pd.Timestamp(date+' 16:59', tz=_EST))]
        if len(day) < 15: continue
        try:
            result = run_trading_algo_fast(day, date, '09:30', '17:00', config=cfg)
            pl = float(result['session_pl'].iloc[-1])
            total_pl += pl; days += 1
            if pl > 0: wins += 1
        except: pass
    avg = total_pl/days if days else 0
    win_pct = wins/days*100 if days else 0
    return avg, win_pct, wins, days-wins

t0 = time.time()
base_avg, base_win, base_wins, base_loses = run_config()
print(f'Baseline: {base_avg:+.1f} pts/day  {base_win:.1f}% win  wins={base_wins} loses={base_loses}  ({time.time()-t0:.0f}s)', flush=True)
print(flush=True)

sweeps = [
    ('steep_angle_threshold', [70.0, 72.5, 75.0, 77.5, 80.0, 85.0, 90.0]),
    ('proximity_points',      [4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 12.0]),
    ('warmup_minutes',        [5, 6, 7, 8, 9, 10, 11]),
    ('swing_anchor_threshold',[10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0]),
]

for param, vals in sweeps:
    print(f'--- {param} ---', flush=True)
    best_v = BASE[param]; best_a = base_avg
    for v in vals:
        avg, win_pct, wins, loses = run_config(**{param: v})
        mk = ' <' if avg > best_a else ''
        if avg > best_a: best_a = avg; best_v = v
        print(f'  {param}={v}  avg={avg:+.1f}  win={win_pct:.1f}%  wins={wins}  loses={loses}{mk}', flush=True)
    print(f'  BEST: {best_v}  ({best_a:+.1f})', flush=True)
    print(flush=True)
