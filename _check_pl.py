"""Check final P/L for May 12"""
import pandas as pd
import pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

fpath = r"C:\Users\Administrator\Desktop\2YearsData\full_day\CBOT_MINI_YM1_2026-05-12.csv"
df = pd.read_csv(fpath, index_col=0, parse_dates=True)
est = pytz.timezone("US/Eastern")
df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)

# Filter to day session
day_start = pd.Timestamp("2026-05-12 09:30", tz=est)
day_end = pd.Timestamp("2026-05-12 17:00", tz=est)
df = df[(df.index >= day_start) & (df.index <= day_end)]

config = AlgoConfig(
    warmup_minutes=5,
    steep_angle_threshold=65.0,
    proximity_points=8.0,
    min_reversal_minutes=0,
    min_entry_angle=15.0,
    partial_tp_pts=50.0,
    spike_profit_pts=50.0,
    spike_profit_bars=9,
    wm_shield_distance=0.0,
    steep_line_reentry=False,
    steep_line_proximity=0.0,
    steep_line_exit_only=False,
)

result = run_trading_algo_fast(df, target_date="2026-05-12", start_time="09:30", end_time="17:00", config=config)

print("\nLast 10 bars:")
print(result[['Close', 'signal', 'position', 'pl', 'session_pl']].tail(10))
print(f"\nFinal session_pl: {result['session_pl'].iloc[-1]:.0f} pts")
