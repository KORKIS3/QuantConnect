"""
Debug script to analyze the duplicate SELL at 10:19 on May 12, 2026
"""
import sys
import os
import pandas as pd
import numpy as np
from pathlib import Path

# Clear all caches first
print("Clearing Python caches...")
os.system('python clear_numba_cache.py')

from TradingAlgoFast import run_trading_algo_fast, AlgoConfig

def debug_1019_sell():
    """Analyze bars around 10:19 to find duplicate SELL"""
    
    # Load May 12, 2026 data
    csv_path = Path.home() / "Desktop" / "2YearsData" / "full_day" / "CBOT_MINI_YM1_2026-05-12.csv"
    
    if not csv_path.exists():
        print(f"ERROR: File not found: {csv_path}")
        return
    
    df = pd.read_csv(csv_path)
    df['time'] = pd.to_datetime(df['time'])
    df.set_index('time', inplace=True)
    
    # Current config
    config = AlgoConfig(
        warmup_minutes=5,
        steep_angle_threshold=65.0,
        steep_line_proximity=5.0,
        min_reversal_minutes=0,
        min_entry_angle=15.0,
        partial_tp_pts=50.0,
        spike_profit_pts=50.0,
        wm_shield_distance=12.0
    )
    
    # Run algo
    print("\n" + "="*80)
    print("Running algo on May 12, 2026...")
    print("="*80)
    
    results = run_trading_algo_fast(
        df,
        target_date="2026-05-12",
        start_time="09:30",
        end_time="17:00",
        config=config
    )
    
    # Extract signal info from results DataFrame
    buy_signals = results[results['signal'] == 'BUY']
    sell_signals = results[results['signal'] == 'SELL']
    
    # Get position debug column
    position = results['pos_debug'].values
    
    # Find all signals
    all_signals = results[results['signal'].isin(['BUY', 'SELL'])].copy()
    
    print(f"\nTotal signals: {len(all_signals)}")
    print("\nAll signals:")
    print("-" * 120)
    print(f"{'Bar':<5} {'Time':<10} {'Signal':<6} {'Price':<10} {'Pos After':<10}")
    print("-" * 120)
    
    for idx, row in all_signals.iterrows():
        time_str = str(idx.time())
        sig = row['signal']
        price = row['Close']
        pos = row['pos_debug']
        
        print(f"{results.index.get_loc(idx):<5} {time_str:<10} {sig:<6} {price:<10.1f} {pos:<10}")
    
    # Focus on 10:10 - 10:30 window
    print("\n" + "="*80)
    print("DETAILED ANALYSIS: 10:10 - 10:30 window")
    print("="*80)
    
    start_time = pd.Timestamp('2026-05-12 10:10:00', tz='US/Eastern')
    end_time = pd.Timestamp('2026-05-12 10:30:00', tz='US/Eastern')
    
    window_df = results[(results.index >= start_time) & (results.index <= end_time)].copy()
    
    print(f"\n{'Bar':<5} {'Time':<10} {'Close':<10} {'Signal':<6} {'Pos':<5}")
    print("-" * 120)
    
    for idx, row in window_df.iterrows():
        time_str = str(idx.time())
        close = row['Close']
        sig = row['signal'] if row['signal'] in ['BUY', 'SELL'] else ''
        pos = row['pos_debug']
        
        bar_num = results.index.get_loc(idx)
        print(f"{bar_num:<5} {time_str:<10} {close:<10.1f} {sig:<6} {pos:<5}")
    
    # Check for duplicate SELLs
    print("\n" + "="*80)
    print("DUPLICATE SELL CHECK")
    print("="*80)
    
    duplicate_found = False
    
    for i in range(1, len(all_signals)):
        current_row = all_signals.iloc[i]
        current_idx = all_signals.index[i]
        current_bar = results.index.get_loc(current_idx)
        
        # Get position BEFORE this signal
        prev_bar = current_bar - 1
        if prev_bar >= 0:
            pos_before = results.iloc[prev_bar]['pos_debug']
        else:
            pos_before = 0
        
        time_str = str(current_idx.time())
        sig = current_row['signal']
        pos_after = current_row['pos_debug']
        
        if sig == "SELL" and pos_before == -1:
            print(f"\n⚠️  DUPLICATE SELL FOUND at bar {current_bar} ({time_str})")
            print(f"   Position before: {pos_before} (already SHORT)")
            print(f"   Signal: SELL")
            print(f"   Position after: {pos_after}")
            duplicate_found = True
            
            # Show context
            print(f"\n   Context (bars {current_bar-2} to {current_bar+2}):")
            for j in range(max(0, current_bar-2), min(len(results), current_bar+3)):
                row_j = results.iloc[j]
                t = str(results.index[j].time())
                c = row_j['Close']
                p = row_j['pos_debug']
                s = row_j['signal'] if row_j['signal'] in ['BUY', 'SELL'] else ''
                marker = " <-- DUPLICATE" if j == current_bar else ""
                print(f"   Bar {j}: {t} close={c:.1f} pos={p} sig={s:4}{marker}")
    
    if not duplicate_found:
        print("\n✓ No duplicate SELLs found (position was not already SHORT before SELL)")
    
    print("\n" + "="*80)

if __name__ == "__main__":
    debug_1019_sell()
