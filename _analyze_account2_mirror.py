"""Analyze Account 2 mirror performance vs Account 1."""

import re
from datetime import datetime

# Parse Account 1 log
account1_trades = []
with open(r"C:\Users\Administrator\Desktop\IB_Live\logs\fred_ib_DUO158495_20260514_0934.log", 'r', encoding='utf-8') as f:
    for line in f:
        if 'execDetails Execution' in line and 'DUO158495' in line:
            # Extract time, side, shares, price
            time_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
            side_match = re.search(r"side='(\w+)'", line)
            shares_match = re.search(r"shares=([\d.]+)", line)
            price_match = re.search(r"price=([\d.]+)", line)
            
            if all([time_match, side_match, shares_match, price_match]):
                account1_trades.append({
                    'time': datetime.strptime(time_match.group(1), '%Y-%m-%d %H:%M:%S'),
                    'side': side_match.group(1),
                    'shares': float(shares_match.group(1)),
                    'price': float(price_match.group(1))
                })

# Parse Account 2 log
account2_trades = []
with open(r"C:\Users\Administrator\Desktop\IB_Live\logs\fred_mirror_DUQ921172_20260514_0934.log", 'r', encoding='utf-8') as f:
    for line in f:
        if 'execDetails Execution' in line and 'DUQ921172' in line:
            time_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
            side_match = re.search(r"side='(\w+)'", line)
            shares_match = re.search(r"shares=([\d.]+)", line)
            price_match = re.search(r"price=([\d.]+)", line)
            
            if all([time_match, side_match, shares_match, price_match]):
                account2_trades.append({
                    'time': datetime.strptime(time_match.group(1), '%Y-%m-%d %H:%M:%S'),
                    'side': side_match.group(1),
                    'shares': float(shares_match.group(1)),
                    'price': float(price_match.group(1))
                })

print("=" * 80)
print("ACCOUNT 1 (DUO158495) - MASTER ALGO")
print("=" * 80)
for i, trade in enumerate(account1_trades, 1):
    print(f"{i}. {trade['time'].strftime('%H:%M:%S')} - {trade['side']:3s} {int(trade['shares'])} @ {trade['price']:.0f}")

print("\n" + "=" * 80)
print("ACCOUNT 2 (DUQ921172) - MIRROR")
print("=" * 80)
for i, trade in enumerate(account2_trades, 1):
    print(f"{i}. {trade['time'].strftime('%H:%M:%S')} - {trade['side']:3s} {int(trade['shares'])} @ {trade['price']:.0f}")

print("\n" + "=" * 80)
print("SLIPPAGE ANALYSIS")
print("=" * 80)

total_slippage_pts = 0
total_slippage_usd = 0

for i in range(min(len(account1_trades), len(account2_trades))):
    t1 = account1_trades[i]
    t2 = account2_trades[i]
    
    time_diff = (t2['time'] - t1['time']).total_seconds()
    
    # Calculate slippage (positive = Account 2 worse)
    if t1['side'] == 'BOT':  # Buying - higher price is worse
        slippage_pts = t2['price'] - t1['price']
    else:  # Selling - lower price is worse
        slippage_pts = t1['price'] - t2['price']
    
    slippage_usd = slippage_pts * 0.5 * t1['shares']  # $0.50 per point per contract
    
    total_slippage_pts += slippage_pts
    total_slippage_usd += slippage_usd
    
    print(f"\nTrade {i+1}:")
    print(f"  Account 1: {t1['time'].strftime('%H:%M:%S')} {t1['side']:3s} {int(t1['shares'])} @ {t1['price']:.0f}")
    print(f"  Account 2: {t2['time'].strftime('%H:%M:%S')} {t2['side']:3s} {int(t2['shares'])} @ {t2['price']:.0f}")
    print(f"  Time lag: {time_diff:.1f} seconds")
    print(f"  Slippage: {slippage_pts:+.0f} pts = ${slippage_usd:+.2f}")

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"Total trades: Account 1 = {len(account1_trades)}, Account 2 = {len(account2_trades)}")
print(f"Total slippage: {total_slippage_pts:+.0f} points = ${total_slippage_usd:+.2f}")
print(f"Average slippage per trade: {total_slippage_pts/len(account2_trades):+.1f} points = ${total_slippage_usd/len(account2_trades):+.2f}")

# Calculate P/L difference
print("\n" + "=" * 80)
print("P/L COMPARISON")
print("=" * 80)

# From the logs
account1_realized_pnl = -39.48  # From commission report after first reversal
account2_realized_pnl = 465.08  # From final portfolio update

print(f"Account 1 realized P/L: ${account1_realized_pnl:.2f}")
print(f"Account 2 realized P/L: ${account2_realized_pnl:.2f}")
print(f"Difference: ${account2_realized_pnl - account1_realized_pnl:+.2f}")
print(f"\nNote: Account 2 appears better due to better fills on some trades,")
print(f"but this is inconsistent and unreliable for mirroring.")
