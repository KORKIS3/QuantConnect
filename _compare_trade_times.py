"""Compare trade execution times between Account 1 and Account 2"""
import re
from datetime import datetime

def extract_executions(log_file):
    """Extract all executions with timestamps"""
    executions = []
    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # Pattern: timestamp, side (BOT/SLD), shares, price
    pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?side=\'(BOT|SLD)\', shares=([\d.]+), price=([\d.]+)'
    matches = re.findall(pattern, content)
    
    for match in matches:
        timestamp_str, side, shares, price = match
        executions.append({
            'time': datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S'),
            'side': 'BUY' if side == 'BOT' else 'SELL',
            'shares': float(shares),
            'price': float(price)
        })
    
    return executions

# Load both accounts
acc1_execs = extract_executions(r'C:\Users\Administrator\Desktop\IB_Live\logs\fred_ib_DUO158495_20260514_0934.log')
acc2_execs = extract_executions(r'C:\Users\Administrator\Desktop\IB_Live\logs\fred_mirror_DUQ921172_20260514_0934.log')

print("=" * 100)
print("TRADE EXECUTION TIME COMPARISON")
print("=" * 100)
print(f"{'#':<4} {'Acc1 Time':<20} {'Acc1':<5} {'Acc1 Price':<12} {'Acc2 Time':<20} {'Acc2':<5} {'Acc2 Price':<12} {'Delay (sec)':<12} {'Price Diff':<10}")
print("-" * 100)

# Compare first 20 trades
for i in range(min(20, len(acc1_execs), len(acc2_execs))):
    acc1 = acc1_execs[i]
    acc2 = acc2_execs[i]
    
    time_diff = (acc2['time'] - acc1['time']).total_seconds()
    price_diff = acc2['price'] - acc1['price']
    
    match = "✓" if acc1['side'] == acc2['side'] else "✗"
    
    print(f"{i+1:<4} {acc1['time'].strftime('%H:%M:%S'):<20} {acc1['side']:<5} {acc1['price']:<12.1f} "
          f"{acc2['time'].strftime('%H:%M:%S'):<20} {acc2['side']:<5} {acc2['price']:<12.1f} "
          f"{time_diff:<12.1f} {price_diff:+10.1f} {match}")

print("\n" + "=" * 100)
print("SUMMARY")
print("=" * 100)

if len(acc1_execs) > 0 and len(acc2_execs) > 0:
    delays = [(acc2_execs[i]['time'] - acc1_execs[i]['time']).total_seconds() 
              for i in range(min(len(acc1_execs), len(acc2_execs)))]
    
    avg_delay = sum(delays) / len(delays)
    min_delay = min(delays)
    max_delay = max(delays)
    
    print(f"Average delay: {avg_delay:.2f} seconds")
    print(f"Min delay: {min_delay:.2f} seconds")
    print(f"Max delay: {max_delay:.2f} seconds")
    
    price_diffs = [abs(acc2_execs[i]['price'] - acc1_execs[i]['price']) 
                   for i in range(min(len(acc1_execs), len(acc2_execs)))]
    avg_price_diff = sum(price_diffs) / len(price_diffs)
    print(f"\nAverage price difference: {avg_price_diff:.2f} points")
