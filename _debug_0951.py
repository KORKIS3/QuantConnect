import os, pandas as pd, pytz
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig
_EST = pytz.timezone('US/Eastern')
date = '2026-04-29'
track_path = os.path.expanduser('~/Desktop/IB_Live/tracking/YM_tracking_2026-04-29.csv')
df = pd.read_csv(track_path, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
ds = pd.Timestamp('2026-04-29 09:30', tz=_EST)
de = pd.Timestamp('2026-04-29 17:00', tz=_EST)
df = df[(df.index >= ds) & (df.index <= de)]
config = AlgoConfig(warmup_minutes=12, steep_angle_threshold=70.0, proximity_points=15.0, min_reversal_minutes=0, min_entry_angle=30.0)
algo_df = run_trading_algo_fast(df, date, '09:30', '17:00', config=config)
w = algo_df.between_time('09:40', '09:56')
print(f"{'Time':<8} {'Close':>7} {'Purple':>8} {'Blue':>8} {'P_ang':>6} {'B_ang':>6} {'Signal':<8} {'Pos':<6}")
print('-'*65)
for ts, row in w.iterrows():
    sig = row.get('signal','') or ''
    pa = row['purple_angle'][-1] if isinstance(row['purple_angle'], list) else float(row['purple_angle'])
    ba = row['blue_angle'][-1] if isinstance(row['blue_angle'], list) else float(row['blue_angle'])
    t = ts.strftime('%H:%M')
    print(f"{t:<8} {row['Close']:>7.0f} {row['purple_ray']:>8.0f} {row['blue_ray']:>8.0f} {pa:>6.1f} {ba:>6.1f} {sig:<8} {str(row['position']):<6}")
