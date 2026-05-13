"""
Detailed debug of bar 10:19 on May 12, 2026
"""
import pandas as pd
import pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

# Load data
fpath = r"C:\Users\Administrator\Desktop\2YearsData\full_day\CBOT_MINI_YM1_2026-05-12.csv"
df = pd.read_csv(fpath, index_col=0, parse_dates=True)
est = pytz.timezone("US/Eastern")
df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)

# Filter to day session
day_start = pd.Timestamp("2026-05-12 09:30", tz=est)
day_end = pd.Timestamp("2026-05-12 17:00", tz=est)
df = df[(df.index >= day_start) & (df.index <= day_end)]

# Config matching validation script
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
    steep_line_proximity=5.0,
    steep_line_exit_only=False,
)

# Run algo
result = run_trading_algo_fast(df, target_date="2026-05-12", start_time="09:30", end_time="17:00", config=config)

# Focus on 10:10-10:30
start_time = pd.Timestamp("2026-05-12 10:10:00", tz=est)
end_time = pd.Timestamp("2026-05-12 10:30:00", tz=est)
window = result[(result.index >= start_time) & (result.index <= end_time)].copy()

print("\n" + "="*120)
print("DETAILED BAR-BY-BAR ANALYSIS: 10:10 - 10:30")
print("="*120)
print(f"{'Time':<10} {'Close':<10} {'Signal':<6} {'Pos':<5} {'Position':<10} {'Session PL':<12}")
print("-"*120)

for idx, row in window.iterrows():
    time_str = idx.strftime("%H:%M")
    close = row['Close']
    signal = row['signal'] if row['signal'] in ['BUY', 'SELL'] else ''
    pos_debug = row['pos_debug']
    position = row['position']
    session_pl = row['session_pl']
    
    marker = " <-- DUPLICATE?" if time_str == "10:19" and signal == "SELL" else ""
    print(f"{time_str:<10} {close:<10.1f} {signal:<6} {pos_debug:<5} {position:<10} {session_pl:<12.1f}{marker}")

# Show all signals in the window
signals_in_window = window[window['signal'].isin(['BUY', 'SELL'])]
print("\n" + "="*120)
print("SIGNALS IN WINDOW:")
print("="*120)
for idx, row in signals_in_window.iterrows():
    time_str = idx.strftime("%H:%M")
    signal = row['signal']
    price = row['buy_price'] if signal == 'BUY' else row['sell_price']
    pos_before_idx = result.index.get_loc(idx) - 1
    pos_before = result.iloc[pos_before_idx]['pos_debug'] if pos_before_idx >= 0 else 0
    pos_after = row['pos_debug']
    
    print(f"{time_str}: {signal} @ {price:.0f} | pos_before={pos_before} pos_after={pos_after}")

