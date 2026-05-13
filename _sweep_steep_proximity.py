"""Sweep steep_line_proximity parameter: 0, 5, 10, 15, 20"""
import subprocess
import sys

def clear_numba_cache():
    """Run the full nuclear cache clear script"""
    print("  Clearing all caches...")
    result = subprocess.run([sys.executable, "clear_numba_cache.py"], 
                          capture_output=True, text=True)
    if result.returncode == 0:
        print("  Cache cleared successfully")
    else:
        print(f"  Cache clear failed: {result.stderr}")

proximity_values = [0, 5, 10, 15, 20]

print("="*80)
print("STEEP LINE PROXIMITY SWEEP")
print("="*80)
print(f"Testing values: {proximity_values}")
print("="*80)

results = {}

for prox in proximity_values:
    print(f"\n{'='*80}")
    print(f"Running backtest with steep_line_proximity = {prox}")
    print(f"{'='*80}")
    
    # Clear all caches before each run
    clear_numba_cache()
    
    cmd = [
        sys.executable,
        "Backtest2Year.py",
        "--skip-download",
        "--steep-line-proximity",
        str(prox)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # Parse the 17:00 result from output
    for line in result.stdout.split('\n'):
        if line.startswith('17:00'):
            parts = line.split()
            if len(parts) >= 8:
                days = int(parts[1])
                win = int(parts[2])
                lose = int(parts[3])
                win_pct = parts[4]
                pts = int(parts[5])
                avg_day = parts[8]
                results[prox] = {
                    'days': days,
                    'win': win,
                    'lose': lose,
                    'win_pct': win_pct,
                    'pts': pts,
                    'avg_day': avg_day
                }
                break

print("\n" + "="*80)
print("SWEEP RESULTS SUMMARY (17:00 end time)")
print("="*80)
print(f"{'Proximity':<12} {'Days':<8} {'Win':<8} {'Lose':<8} {'Win%':<10} {'Total Pts':<12} {'Avg/Day':<10}")
print("-"*80)

for prox in proximity_values:
    if prox in results:
        r = results[prox]
        print(f"{prox:<12} {r['days']:<8} {r['win']:<8} {r['lose']:<8} {r['win_pct']:<10} {r['pts']:<12} {r['avg_day']:<10}")
    else:
        print(f"{prox:<12} NO DATA")

print("="*80)

# Find best
if results:
    best_prox = max(results.keys(), key=lambda k: results[k]['pts'])
    print(f"\nBest proximity: {best_prox} pts → {results[best_prox]['avg_day']} avg/day")
