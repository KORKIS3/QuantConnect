"""Create a visual chart comparing Account 1 and Account 2 trades"""
import re
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

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

# Create figure with 2 subplots
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10), sharex=True)

# Plot Account 1
acc1_times = [e['time'] for e in acc1_execs]
acc1_prices = [e['price'] for e in acc1_execs]
acc1_colors = ['green' if e['side'] == 'BUY' else 'red' for e in acc1_execs]
acc1_markers = ['^' if e['side'] == 'BUY' else 'v' for e in acc1_execs]

for i, (time, price, color, marker) in enumerate(zip(acc1_times, acc1_prices, acc1_colors, acc1_markers)):
    ax1.scatter(time, price, c=color, marker=marker, s=100, alpha=0.7, edgecolors='black', linewidths=1)
    if i > 0:
        ax1.plot([acc1_times[i-1], time], [acc1_prices[i-1], price], 'b-', alpha=0.3, linewidth=1)

ax1.set_ylabel('Price', fontsize=12, fontweight='bold')
ax1.set_title('Account 1 (DUO158495) - Primary Trading Account', fontsize=14, fontweight='bold')
ax1.grid(True, alpha=0.3)
ax1.legend(['BUY', 'SELL'], loc='upper right')

# Plot Account 2
acc2_times = [e['time'] for e in acc2_execs]
acc2_prices = [e['price'] for e in acc2_execs]
acc2_colors = ['green' if e['side'] == 'BUY' else 'red' for e in acc2_execs]
acc2_markers = ['^' if e['side'] == 'BUY' else 'v' for e in acc2_execs]

for i, (time, price, color, marker) in enumerate(zip(acc2_times, acc2_prices, acc2_colors, acc2_markers)):
    ax2.scatter(time, price, c=color, marker=marker, s=100, alpha=0.7, edgecolors='black', linewidths=1)
    if i > 0:
        ax2.plot([acc2_times[i-1], time], [acc2_prices[i-1], price], 'b-', alpha=0.3, linewidth=1)

ax2.set_ylabel('Price', fontsize=12, fontweight='bold')
ax2.set_xlabel('Time', fontsize=12, fontweight='bold')
ax2.set_title('Account 2 (DUQ921172) - Mirror Account', fontsize=14, fontweight='bold')
ax2.grid(True, alpha=0.3)
ax2.legend(['BUY', 'SELL'], loc='upper right')

# Format x-axis
ax2.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
ax2.xaxis.set_major_locator(mdates.MinuteLocator(interval=30))
plt.xticks(rotation=45)

# Add summary text
summary_text = f"""
Account 1: {len(acc1_execs)} executions | Final P/L: -$452.76
Account 2: {len(acc2_execs)} executions | Final P/L: +$674.74
P/L Difference: +$1,127.50
"""
fig.text(0.5, 0.02, summary_text, ha='center', fontsize=10, 
         bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

plt.tight_layout(rect=[0, 0.05, 1, 1])
plt.savefig('account_comparison_chart.png', dpi=150, bbox_inches='tight')
print("Chart saved as: account_comparison_chart.png")
plt.show()
