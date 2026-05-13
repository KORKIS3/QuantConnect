"""Interactive chart for May 12, 2026 - DAY SESSION ONLY"""
import pandas as pd
import pytz
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast
from plotFigure import plot_intraday_data

# Load May 12 data
fpath = r"C:\Users\Administrator\Desktop\2YearsData\full_day\CBOT_MINI_YM1_2026-05-12.csv"
df = pd.read_csv(fpath, index_col=0, parse_dates=True)
est = pytz.timezone("US/Eastern")
df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)

# Filter to DAY SESSION ONLY (9:30-17:00)
day_start = pd.Timestamp("2026-05-12 09:30", tz=est)
day_end = pd.Timestamp("2026-05-12 17:00", tz=est)
df = df[(df.index >= day_start) & (df.index <= day_end)]
print(f"Day session bars: {len(df)} (9:30-17:00)")

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

# Run algo
result = run_trading_algo_fast(
    df, 
    target_date="2026-05-12",
    start_time="09:30",
    end_time="17:00",
    config=config
)

# Show final P/L
final_pl = result['session_pl'].iloc[-1]
print(f"\nDay session final P/L: {final_pl:.0f} pts")

# Launch interactive chart
plot_intraday_data(result, "2026-05-12", "09:30", "17:00")
