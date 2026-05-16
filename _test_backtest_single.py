"""Test backtest on single day to see error"""
import sys
import traceback
from Backtest2Year import _process_day

# Test one day
fname = "CBOT_MINI_YM1_2024-01-02.csv"

try:
    date_str, result = _process_day(fname, quick=False, steep_line_proximity=5.0, steep_line_exit_only=False)
    print(f"SUCCESS: {date_str}")
    print(f"Results: {result}")
except Exception as e:
    print(f"CRASH: {e}")
    traceback.print_exc()
