"""Test if disable_steep_lines actually works"""
import os
import pandas as pd
import pytz
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig

_EST = pytz.timezone("US/Eastern")
_DATA_ROOT = os.path.expanduser("~/Desktop/2YearsData/full_day")

# Pick a single day to test
test_file = "CBOT_MINI_YM1_2026-05-12.csv"
fpath = os.path.join(_DATA_ROOT, test_file)

df = pd.read_csv(fpath, index_col=0, parse_dates=True)
df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)

print("Testing with steep lines ENABLED:")
config_enabled = AlgoConfig(
    warmup_minutes=12,
    steep_angle_threshold=70.0,
    proximity_points=15.0,
    min_reversal_minutes=0,
    min_entry_angle=0.0,
    partial_tp_pts=50.0,
    spike_profit_pts=100.0,
    spike_profit_bars=9,
    wm_shield_distance=12.0,
    steep_line_reentry=False,
    steep_line_proximity=5.0,
    steep_line_exit_only=False,
    disable_steep_lines=False,  # ENABLED
    num_contracts=2,
)

result_enabled = run_trading_algo_fast(df, "2026-05-12", "09:30", "17:00", config=config_enabled)
if result_enabled is not None:
    signals_enabled = result_enabled[result_enabled['signal'].notna()]
    buy_signals_enabled = len(signals_enabled[signals_enabled['signal'] == 'BUY'])
    sell_signals_enabled = len(signals_enabled[signals_enabled['signal'] == 'SELL'])
    print(f"  Total trades: {buy_signals_enabled + sell_signals_enabled} (BUY: {buy_signals_enabled}, SELL: {sell_signals_enabled})")
    print(f"  Final P/L: {result_enabled['session_pl'].iloc[-1]:.0f} pts")

print("\nTesting with steep lines DISABLED:")
config_disabled = AlgoConfig(
    warmup_minutes=12,
    steep_angle_threshold=70.0,
    proximity_points=15.0,
    min_reversal_minutes=0,
    min_entry_angle=0.0,
    partial_tp_pts=50.0,
    spike_profit_pts=100.0,
    spike_profit_bars=9,
    wm_shield_distance=12.0,
    steep_line_reentry=False,
    steep_line_proximity=5.0,
    steep_line_exit_only=False,
    disable_steep_lines=True,  # DISABLED
    num_contracts=2,
)

result_disabled = run_trading_algo_fast(df, "2026-05-12", "09:30", "17:00", config=config_disabled)
if result_disabled is not None:
    signals_disabled = result_disabled[result_disabled['signal'].notna()]
    buy_signals_disabled = len(signals_disabled[signals_disabled['signal'] == 'BUY'])
    sell_signals_disabled = len(signals_disabled[signals_disabled['signal'] == 'SELL'])
    print(f"  Total trades: {buy_signals_disabled + sell_signals_disabled} (BUY: {buy_signals_disabled}, SELL: {sell_signals_disabled})")
    print(f"  Final P/L: {result_disabled['session_pl'].iloc[-1]:.0f} pts")

print("\n" + "="*60)
total_enabled = buy_signals_enabled + sell_signals_enabled
total_disabled = buy_signals_disabled + sell_signals_disabled
if total_enabled > total_disabled:
    print(f"SUCCESS: Steep lines disabled reduced trades from {total_enabled} to {total_disabled}")
    print(f"That's a {total_enabled - total_disabled} trade reduction ({((total_enabled - total_disabled) / total_enabled * 100):.1f}% fewer trades)")
else:
    print(f"FAILURE: Trade count unchanged ({total_enabled} vs {total_disabled})")
    print("The disable_steep_lines parameter is NOT working!")
