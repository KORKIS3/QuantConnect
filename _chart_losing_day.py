"""Run Pinball v6 on a big losing day and show interactive chart."""
import pandas as pd, pytz, os
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast
from plotFigure import plot_intraday_data

_EST = pytz.timezone('US/Eastern')
data_root = os.path.expanduser('~/Desktop/2YearsData/full_day')

target_date = '2025-03-11'  # -650 worst day in v6

fpath = os.path.join(data_root, f'CBOT_MINI_YM1_{target_date}.csv')
df = pd.read_csv(fpath, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)

day_start = pd.Timestamp(f'{target_date} 09:30', tz=_EST)
day_end = pd.Timestamp(f'{target_date} 16:59', tz=_EST)
day_data = df[(df.index >= day_start) & (df.index <= day_end)]

config = AlgoConfig(
    warmup_minutes=7,
    steep_angle_threshold=90.0,
    proximity_points=4.0,
    min_reversal_minutes=0,
    min_entry_angle=0.0,
    partial_tp_pts=50.0,
    wm_shield_distance=0.0,
    swing_anchor_threshold=10.0,
)

print(f"Running chart for {target_date} (big losing day)...")
algo_df = run_trading_algo_fast(day_data, target_date, '09:30', '17:00', config=config)
print(f"Algo done: {len(algo_df)} bars, final PL={algo_df['session_pl'].iloc[-1]:.0f}")

plot_intraday_data(algo_df, target_date, '09:30', '17:00')
