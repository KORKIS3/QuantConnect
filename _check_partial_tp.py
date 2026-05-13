"""Check partial TP events for May 12, 2026"""
import pandas as pd
import pytz
from pathlib import Path
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast

csv_path = Path.home() / "Desktop" / "2YearsData" / "full_day" / "CBOT_MINI_YM1_2026-05-12.csv"
df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
est = pytz.timezone("US/Eastern")
df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)

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
    steep_line_proximity=5.0,
    steep_line_exit_only=False,
)

result = run_trading_algo_fast(df, target_date="2026-05-12", start_time="09:30", end_time="17:00", config=config)

# Check partial TP events
partial_tp_events = result[result['partial_tp'] == True]

print(f"\nPartial TP events: {len(partial_tp_events)}")
print(f"Total partial TP P/L: {len(partial_tp_events) * 50} pts")

if len(partial_tp_events) > 0:
    print("\nPartial TP times:")
    for idx in partial_tp_events.index:
        print(f"  {idx.strftime('%H:%M')}")

print(f"\nFinal session P/L: {result.iloc[-1]['session_pl']:.1f} pts")
