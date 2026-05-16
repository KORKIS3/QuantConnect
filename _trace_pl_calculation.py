"""Trace P/L calculation to verify contracts_remaining logic executes"""
import pandas as pd
import pytz
from pathlib import Path
import sys

# Monkey-patch to trace execution
original_run = None

def traced_run(*args, **kwargs):
    """Wrapper to trace execution"""
    print("\n=== TRACE: run_trading_algo_fast called ===")
    print(f"Args: {len(args)}")
    print(f"Kwargs: {list(kwargs.keys())}")
    if 'config' in kwargs:
        cfg = kwargs['config']
        print(f"Config.num_contracts: {cfg.num_contracts}")
        print(f"Config.partial_tp_pts: {cfg.partial_tp_pts}")
        print(f"Config.steep_line_proximity: {cfg.steep_line_proximity}")
    
    result = original_run(*args, **kwargs)
    
    # Analyze result
    signals = result[result['signal'].notna()]
    print(f"\n=== TRACE: Signals generated: {len(signals)} ===")
    for idx, row in signals.head(5).iterrows():
        print(f"  {idx}: {row['signal']} @ {row['Close']:.0f}")
    
    final_pl = result.iloc[-1]['session_pl']
    print(f"\n=== TRACE: Final P/L: {final_pl:.1f} pts ===")
    
    return result

# Import and patch
from TradingAlgoFast import AlgoConfig, run_trading_algo_fast
original_run = run_trading_algo_fast
sys.modules['TradingAlgoFast'].run_trading_algo_fast = traced_run

# Now run backtest on one day
date_str = "2024-01-02"
csv_path = Path.home() / "Desktop" / "2YearsData" / "full_day" / f"CBOT_MINI_YM1_{date_str}.csv"

print(f"Loading: {csv_path}")
df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
est = pytz.timezone('US/Eastern')
df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)

# Filter to day session
day_start = pd.Timestamp(f"{date_str} 09:30", tz=est)
day_end = pd.Timestamp(f"{date_str} 17:00", tz=est)
df = df[(df.index >= day_start) & (df.index <= day_end)]

print(f"Bars: {len(df)}")

# Run with traced function
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
    num_contracts=2,
)

result = traced_run(df, target_date=date_str, start_time="09:30", end_time="17:00", config=config)

print("\n=== TRACE COMPLETE ===")
