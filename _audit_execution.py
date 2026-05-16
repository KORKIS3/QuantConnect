"""Forensic audit: Verify which code is actually executing"""
import sys
import os
import hashlib
from pathlib import Path
from datetime import datetime

print("="*80)
print("FORENSIC AUDIT: Code Execution Verification")
print("="*80)

# 1. File paths and hashes
print("\n1. SOURCE FILE VERIFICATION")
print("-" * 80)

files_to_check = [
    "TradingAlgoFast.py",
    "Backtest2Year.py",
    "InteractiveBrokers.py",
]

for fname in files_to_check:
    fpath = Path(fname)
    if fpath.exists():
        stat = fpath.stat()
        with open(fpath, 'rb') as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()
        print(f"{fname}:")
        print(f"  Path: {fpath.absolute()}")
        print(f"  Modified: {datetime.fromtimestamp(stat.st_mtime)}")
        print(f"  Size: {stat.st_size} bytes")
        print(f"  SHA256: {file_hash[:16]}...")
    else:
        print(f"{fname}: NOT FOUND")

# 2. Check __pycache__
print("\n2. BYTECODE CACHE STATUS")
print("-" * 80)
pycache = Path("__pycache__")
if pycache.exists():
    pyc_files = list(pycache.glob("TradingAlgoFast*.pyc"))
    nbc_files = list(pycache.glob("TradingAlgoFast*.nbc"))
    nbi_files = list(pycache.glob("TradingAlgoFast*.nbi"))
    
    print(f"Python bytecode files: {len(pyc_files)}")
    for f in pyc_files:
        stat = f.stat()
        print(f"  {f.name}: {datetime.fromtimestamp(stat.st_mtime)}")
    
    print(f"\nNumba compiled files (.nbc): {len(nbc_files)}")
    for f in sorted(nbc_files)[:5]:  # Show first 5
        stat = f.stat()
        print(f"  {f.name}: {datetime.fromtimestamp(stat.st_mtime)}")
    
    print(f"\nNumba index files (.nbi): {len(nbi_files)}")
    for f in nbi_files:
        stat = f.stat()
        print(f"  {f.name}: {datetime.fromtimestamp(stat.st_mtime)}")
else:
    print("No __pycache__ directory found")

# 3. Import and check loaded module
print("\n3. MODULE IMPORT VERIFICATION")
print("-" * 80)

import TradingAlgoFast
print(f"Module loaded from: {TradingAlgoFast.__file__}")
print(f"Module has AlgoConfig: {hasattr(TradingAlgoFast, 'AlgoConfig')}")
print(f"Module has run_trading_algo_fast: {hasattr(TradingAlgoFast, 'run_trading_algo_fast')}")
print(f"Module has _run_signals_nb: {hasattr(TradingAlgoFast, '_run_signals_nb')}")

# 4. Check function signatures
print("\n4. FUNCTION SIGNATURE VERIFICATION")
print("-" * 80)

import inspect

# Check _run_signals_nb signature
sig = inspect.signature(TradingAlgoFast._run_signals_nb.py_func)
params = list(sig.parameters.keys())
print(f"_run_signals_nb parameters ({len(params)} total):")
print(f"  First 10: {params[:10]}")
print(f"  Last 5: {params[-5:]}")
print(f"  Has 'num_contracts': {'num_contracts' in params}")

# Check AlgoConfig
config = TradingAlgoFast.AlgoConfig()
print(f"\nAlgoConfig default values:")
print(f"  num_contracts: {config.num_contracts}")
print(f"  steep_line_proximity: {config.steep_line_proximity}")
print(f"  partial_tp_pts: {config.partial_tp_pts}")

# 5. Run a single-day backtest with instrumentation
print("\n5. SINGLE-DAY BACKTEST EXECUTION")
print("-" * 80)

import pandas as pd
import pytz

# Load one day of data
date_str = "2026-05-14"
csv_path = Path.home() / "Desktop" / "IB_Live" / "tracking" / f"YM_tracking_DUO158495_{date_str}_0930.csv"

if csv_path.exists():
    print(f"Loading: {csv_path}")
    df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
    est = pytz.timezone('US/Eastern')
    df.index = pd.to_datetime(df.index, utc=True).tz_convert(est)
    
    # Filter to day session
    day_start = pd.Timestamp(f"{date_str} 09:30", tz=est)
    day_end = pd.Timestamp(f"{date_str} 17:00", tz=est)
    df = df[(df.index >= day_start) & (df.index <= day_end)]
    
    print(f"Bars loaded: {len(df)}")
    
    # Run algo
    config = TradingAlgoFast.AlgoConfig(
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
        num_contracts=2,
    )
    
    print(f"\nRunning algo with config:")
    print(f"  num_contracts: {config.num_contracts}")
    print(f"  partial_tp_pts: {config.partial_tp_pts}")
    
    result = TradingAlgoFast.run_trading_algo_fast(
        df, 
        target_date=date_str, 
        start_time="09:30", 
        end_time="17:00", 
        config=config
    )
    
    # Analyze results
    final_pl = result.iloc[-1]['session_pl']
    buy_signals = result[result['signal'] == 'BUY']
    sell_signals = result[result['signal'] == 'SELL']
    
    print(f"\nRESULTS:")
    print(f"  Final P/L: {final_pl:.1f} pts")
    print(f"  BUY signals: {len(buy_signals)}")
    print(f"  SELL signals: {len(sell_signals)}")
    print(f"  Total trades: {len(buy_signals) + len(sell_signals)}")
    
    # Show first 10 signals
    signals = result[result['signal'].notna()]
    print(f"\nFirst 10 signals:")
    for idx, row in signals.head(10).iterrows():
        print(f"  {idx}: {row['signal']} @ {row['Close']:.0f}")
    
else:
    print(f"Data file not found: {csv_path}")

print("\n" + "="*80)
print("AUDIT COMPLETE")
print("="*80)
