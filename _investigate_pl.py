"""Investigate P/L discrepancy between script output and chart display"""
import pandas as pd
import pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

# Load May 12 data
fpath = r"C:\Users\Administrator\Desktop\2YearsData\full_day\CBOT_MINI_YM1_2026-05-12.csv"
df = pd.read_csv(fpath, index_col=0, parse_dates=True)
est = pytz.timezone("US/Eastern")
df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)

print(f"Total bars in file: {len(df)}")
print(f"First bar: {df.index[0]}")
print(f"Last bar: {df.index[-1]}")

# Filter to day session
day_start = pd.Timestamp("2026-05-12 09:30", tz=est)
day_end = pd.Timestamp("2026-05-12 17:00", tz=est)
df_day = df[(df.index >= day_start) & (df.index <= day_end)]

print(f"\nDay session bars (9:30-17:00): {len(df_day)}")
print(f"Day session first bar: {df_day.index[0]}")
print(f"Day session last bar: {df_day.index[-1]}")

# Config from commit 8a15b10
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

# Run algo on day session only
result = run_trading_algo_fast(
    df_day, 
    target_date="2026-05-12",
    start_time="09:30",
    end_time="17:00",
    config=config
)

print(f"\nResult dataframe length: {len(result)}")
print(f"\nLast 5 bars:")
print(result[['Close', 'signal', 'position', 'pl', 'session_pl']].tail())

print(f"\nFinal session_pl from result: {result['session_pl'].iloc[-1]:.0f} pts")
print(f"Final position: {result['position'].iloc[-1]}")
print(f"Final pl (unrealized): {result['pl'].iloc[-1]:.0f} pts")

# Count signals
buy_signals = (result['signal'] == 'BUY').sum()
sell_signals = (result['signal'] == 'SELL').sum()
print(f"\nSignals: {buy_signals}B {sell_signals}S")
