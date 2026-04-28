import sys, os, pytz, pandas as pd
print('sweep starting', flush=True)
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

_EST = pytz.timezone('US/Eastern')
_DATA_ROOT = os.path.join(os.path.expanduser('~'), 'Desktop', '2YearsData', 'full_day')
_CSV_FILES = sorted([f for f in os.listdir(_DATA_ROOT) if f.startswith('CBOT_MINI_YM1_') and f.endswith('.csv')])

def run_config(config):
    total_pl = 0.0; win_days = 0; lose_days = 0; total_days = 0
    for fname in _CSV_FILES:
        date = fname.replace('CBOT_MINI_YM1_','').replace('.csv','')
        df = pd.read_csv(os.path.join(_DATA_ROOT, fname), index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        day = df[(df.index >= pd.Timestamp(date+' 09:30', tz=_EST)) & (df.index <= pd.Timestamp(date+' 16:59', tz=_EST))]
        if len(day) < 15: continue
        try:
            result = run_trading_algo_fast(day, date, '09:30', '17:00', config=config)
            pl = float(result['session_pl'].iloc[-1])
            total_pl += pl; total_days += 1
            if pl > 0: win_days += 1
            else: lose_days += 1
        except Exception as e: print('ERR', date, e, flush=True)
    avg = total_pl / total_days if total_days else 0
    return avg, win_days/total_days*100 if total_days else 0, win_days, lose_days

print('WM     PTP      Avg/Day   Win%   Wins  Loses', flush=True)
print('-'*50, flush=True)
best_avg = -9999; best = None
for wm in [0.0, 4.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0]:
    for ptp in [50.0, 75.0, 100.0, 150.0]:
        cfg = AlgoConfig(warmup_minutes=8, steep_angle_threshold=75.0, proximity_points=8.0,
                         min_reversal_minutes=0, min_entry_angle=0.0, partial_tp_pts=ptp, wm_shield_distance=wm)
        avg, win_pct, wins, loses = run_config(cfg)
        mk = ' <' if avg > best_avg else ''
        if avg > best_avg: best_avg = avg; best = (wm, ptp, avg, win_pct, wins, loses)
        print(f'{wm:6.1f}  {ptp:6.0f}  {avg:+8.1f}  {win_pct:5.1f}%  {wins:5}  {loses:5}{mk}', flush=True)
    print(flush=True)
print(f'Best: wm={best[0]} ptp={best[1]} avg={best[2]:+.1f} win={best[3]:.1f}% wins={best[4]} loses={best[5]}', flush=True)
