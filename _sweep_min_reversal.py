"""
Sweep test for min_reversal_minutes parameter.
Tests values from 0 to 15 minutes to find optimal reversal delay.
"""
import os
import sys
import pandas as pd
import numpy as np
from concurrent.futures import ProcessPoolExecutor
from TradingAlgoFast import run_trading_algo_fast, AlgoConfig

_DATA_ROOT = os.path.expanduser("~/Desktop/2YearsData/full_day")
_EST = "America/New_York"

def process_day(fname, min_reversal_minutes):
    """Process a single day with given min_reversal_minutes."""
    target_date = fname.replace("CBOT_MINI_YM1_", "").replace(".csv", "")
    fpath = os.path.join(_DATA_ROOT, fname)
    
    config = AlgoConfig(
        warmup_minutes=12,
        steep_angle_threshold=70.0,
        proximity_points=15.0,
        min_reversal_minutes=min_reversal_minutes,  # SWEEP THIS
        min_entry_angle=0.0,
        partial_tp_pts=50.0,
        spike_profit_pts=100.0,
        spike_profit_bars=9,
        wm_shield_distance=12.0,
        steep_line_reentry=False,
        steep_line_proximity=5.0,
        steep_line_exit_only=False,
        num_contracts=2,
    )
    
    try:
        df = pd.read_csv(fpath, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_convert(_EST)
        if len(df) < 10:
            return None
        
        day_start = pd.Timestamp(f"{target_date} 09:30", tz=_EST)
        day_end = pd.Timestamp(f"{target_date} 16:59", tz=_EST)
        day_data = df[(df.index >= day_start) & (df.index <= day_end)]
        
        if len(day_data) >= 15:
            result = run_trading_algo_fast(day_data, target_date, "09:30", "17:00", config=config)
            if result is not None and len(result) > 0:
                return float(result["session_pl"].iloc[-1])
    except Exception as e:
        print(f"Error processing {target_date}: {e}")
    
    return None


def main():
    # Get all CSV files
    all_files = sorted([f for f in os.listdir(_DATA_ROOT) if f.endswith(".csv")])
    print(f"Found {len(all_files)} days of data\n")
    
    # Test values: 0, 1, 2, 3, 5, 7, 10, 15 minutes
    test_values = [0, 1, 2, 3, 5, 7, 10, 15]
    
    results = {}
    
    for min_rev in test_values:
        print(f"\nTesting min_reversal_minutes = {min_rev}...")
        
        with ProcessPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(process_day, fname, min_rev) for fname in all_files]
            day_results = [f.result() for f in futures]
        
        # Filter out None values
        valid_results = [r for r in day_results if r is not None and r != 0.0]
        
        if valid_results:
            total_pts = sum(valid_results)
            avg_pts = total_pts / len(valid_results)
            win_days = sum(1 for r in valid_results if r > 0)
            lose_days = sum(1 for r in valid_results if r < 0)
            win_pct = (win_days / len(valid_results)) * 100 if valid_results else 0
            
            results[min_rev] = {
                'days': len(valid_results),
                'total_pts': total_pts,
                'avg_pts': avg_pts,
                'win_days': win_days,
                'lose_days': lose_days,
                'win_pct': win_pct
            }
            
            print(f"  Days: {len(valid_results)}, Avg: {avg_pts:+.1f} pts/day, Win%: {win_pct:.1f}%, Win: {win_days}, Lose: {lose_days}")
    
    # Print summary table
    print("\n" + "="*100)
    print("SWEEP RESULTS: min_reversal_minutes")
    print("="*100)
    print(f"{'Min Rev (min)':<15} {'Days':<8} {'Win%':<8} {'Win':<6} {'Lose':<6} {'Total Pts':<12} {'Avg/Day':<10}")
    print("-"*100)
    
    for min_rev in test_values:
        if min_rev in results:
            r = results[min_rev]
            print(f"{min_rev:<15} {r['days']:<8} {r['win_pct']:<8.1f} {r['win_days']:<6} {r['lose_days']:<6} {r['total_pts']:<12.0f} {r['avg_pts']:<+10.1f}")
    
    print("="*100)
    
    # Find best
    best_min_rev = max(results.keys(), key=lambda k: results[k]['avg_pts'])
    print(f"\nBEST: min_reversal_minutes = {best_min_rev} → {results[best_min_rev]['avg_pts']:+.1f} pts/day")


if __name__ == "__main__":
    main()
