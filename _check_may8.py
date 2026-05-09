import pandas as pd
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

df = pd.read_csv(r'C:\Users\Administrator\Desktop\2YearsData\full_day\CBOT_MINI_YM1_2026-05-08.csv')
df['time'] = pd.to_datetime(df['time'])
df = df.set_index('time')

config = AlgoConfig(
    warmup_minutes=12,
    steep_angle_threshold=70.0,
    proximity_points=15.0,
    min_reversal_minutes=0,
    min_entry_angle=30.0,
    partial_tp_pts=50.0,
    wm_shield_distance=12.0,
    reanchor_blue_purple=True,
    reanchor_min_bars=30
)

result = run_trading_algo_fast(df, '2026-05-08', '09:30', '17:00', config)

print(f'Final P/L: {result["session_pl"].iloc[-1]:.1f} pts')
print(f'Total signals: {result["signal"].notna().sum()}')
print(f'\nSignals:')
signals = result[result["signal"].notna()].reset_index()
print(signals[['time', 'signal', 'buy_price', 'sell_price', 'position', 'session_pl']].to_string(index=False))
