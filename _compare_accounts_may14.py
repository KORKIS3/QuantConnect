"""Compare Account 1 and Account 2 trades for May 14, 2026"""
import re

def extract_trades(log_file):
    """Extract all trades from log file"""
    trades = []
    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
        
    # Find all trade alerts
    pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?\[Email\] Trade alert sent: (BUY|SELL) @ ([\d.]+)'
    matches = re.findall(pattern, content)
    
    for match in matches:
        time, action, price = match
        trades.append({
            'time': time,
            'action': action,
            'price': float(price)
        })
    
    # Find realized P/L
    pl_pattern = r'realizedPNL=([-\d.]+)'
    pl_matches = re.findall(pl_pattern, content)
    final_pl = float(pl_matches[-1]) if pl_matches else 0.0
    
    return trades, final_pl

# Account 1
acc1_trades, acc1_pl = extract_trades(r'C:\Users\Administrator\Desktop\IB_Live\logs\fred_ib_DUO158495_20260514_0934.log')

# Account 2
acc2_trades, acc2_pl = extract_trades(r'C:\Users\Administrator\Desktop\IB_Live\logs\fred_mirror_DUQ921172_20260514_0934.log')

print("=" * 80)
print("ACCOUNT 1 (DUO158495) - Primary Trading Account")
print("=" * 80)
for i, trade in enumerate(acc1_trades, 1):
    print(f"{i}. {trade['time']} - {trade['action']:4s} @ {trade['price']:.2f}")
print(f"\nFinal Realized P/L: ${acc1_pl:.2f}")

print("\n" + "=" * 80)
print("ACCOUNT 2 (DUQ921172) - Mirror Account")
print("=" * 80)
for i, trade in enumerate(acc2_trades, 1):
    print(f"{i}. {trade['time']} - {trade['action']:4s} @ {trade['price']:.2f}")
print(f"\nFinal Realized P/L: ${acc2_pl:.2f}")

print("\n" + "=" * 80)
print("COMPARISON")
print("=" * 80)
print(f"Account 1 trades: {len(acc1_trades)}")
print(f"Account 2 trades: {len(acc2_trades)}")
print(f"P/L difference: ${acc2_pl - acc1_pl:.2f}")

# Find divergence point
print("\nTrade-by-trade comparison:")
for i in range(min(len(acc1_trades), len(acc2_trades))):
    acc1 = acc1_trades[i]
    acc2 = acc2_trades[i]
    match = "✓" if (acc1['action'] == acc2['action'] and abs(acc1['price'] - acc2['price']) < 5) else "✗ DIVERGED"
    print(f"{i+1}. Acc1: {acc1['action']} @ {acc1['price']:.2f}  |  Acc2: {acc2['action']} @ {acc2['price']:.2f}  {match}")
